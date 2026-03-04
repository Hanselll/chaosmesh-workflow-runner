# -*- coding: utf-8 -*-
import os, pty, time, re, select, fcntl, subprocess

def set_nonblocking(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

def read_until(fd, pattern, timeout=10):
    buf=""
    end=time.time()+timeout
    while time.time()<end:
        r,_,_=select.select([fd],[],[],0.5)
        if not r:
            continue
        try:
            data=os.read(fd,4096)
        except BlockingIOError:
            continue
        except OSError:
            break
        if not data:
            break
        buf += data.decode(errors="ignore")
        if re.search(pattern, buf):
            break
    return buf

def extract_ip(text):
    m=re.search(r'addr\\?"\s*:\s*\\?"((?:\d{1,3}\.){3}\d{1,3})', text)
    if m: return m.group(1)
    m2=re.search(r'((?:\d{1,3}\.){3}\d{1,3})', text)
    if m2: return m2.group(1)
    return None

def run_lmt_list_in_container(namespace, pod, container, login_ip, login_port, username, password, table, raw_out_path="/tmp/lmt_raw_pty.txt"):
    master_fd, slave_fd = pty.openpty()
    set_nonblocking(master_fd)

    cmd=["kubectl","exec","-it","-n",namespace,pod,"-c",container,"--","bash","--noprofile","--norc"]
    proc=subprocess.Popen(cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True)
    os.close(slave_fd)

    def send(s): os.write(master_fd, s.encode())

    out=read_until(master_fd, r".*", timeout=1)
    send("echo __READY__\n")
    out += read_until(master_fd, r"__READY__", timeout=8)
    if "__READY__" not in out:
        open(raw_out_path,"w").write(out)
        raise RuntimeError("no __READY__ raw={}".format(raw_out_path))

    send("export HOME=/tmp\n")
    out += read_until(master_fd, r".*", timeout=1)

    send("lmt-cli login --ip {} --port {} --username {}\n".format(login_ip, login_port, username))
    out += read_until(master_fd, r"(Enter Password:|Password:)", timeout=8)
    send(password+"\n")
    out += read_until(master_fd, r"(login success|login failed|status:)", timeout=10)
    if "login success" not in out:
        open(raw_out_path,"w").write(out)
        raise RuntimeError("lmt login failed raw={}".format(raw_out_path))

    send("lmt-cli list {}\n".format(table))
    out += read_until(master_fd, r"(addr|records|totalItems|Error:)", timeout=10)

    send("exit\n"); send("exit\n")
    time.sleep(0.2)
    proc.terminate()
    try: os.close(master_fd)
    except Exception: pass
    open(raw_out_path,"w").write(out)
    return out


def run_lmt_commands_in_container(
    namespace,
    pod,
    container,
    login_ip,
    login_port,
    username,
    password,
    commands,
    raw_out_path="/tmp/lmt_raw_pty_multi.txt",
):
    """Login once then execute commands in interactive PTY.

    Returns:
        {
          "raw_output": "...",
          "results": [{"command": "...", "output": "..."}, ...]
        }
    """
    master_fd, slave_fd = pty.openpty()
    set_nonblocking(master_fd)

    cmd = ["kubectl", "exec", "-it", "-n", namespace, pod, "-c", container, "--", "bash", "--noprofile", "--norc"]
    proc = subprocess.Popen(cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True)
    os.close(slave_fd)

    def send(s):
        os.write(master_fd, s.encode())

    out = read_until(master_fd, r".*", timeout=1)
    send("echo __READY__\n")
    out += read_until(master_fd, r"__READY__", timeout=8)
    if "__READY__" not in out:
        open(raw_out_path, "w").write(out)
        raise RuntimeError("no __READY__ raw={}".format(raw_out_path))

    send("export HOME=/tmp\n")
    out += read_until(master_fd, r".*", timeout=1)

    send("lmt-cli login --ip {} --port {} --username {}\n".format(login_ip, login_port, username))
    out += read_until(master_fd, r"(Enter Password:|Password:)", timeout=8)
    send(password + "\n")
    out += read_until(master_fd, r"(login success|login failed|status:)", timeout=10)
    if "login success" not in out:
        open(raw_out_path, "w").write(out)
        raise RuntimeError("lmt login failed raw={}".format(raw_out_path))

    results = []
    for idx, command in enumerate(commands):
        begin = "__CMD_BEGIN_{}__".format(idx)
        end = "__CMD_END_{}__".format(idx)
        send("echo {b}\n{cmd}\necho {e}\n".format(b=begin, cmd=command, e=end))
        chunk = read_until(master_fd, end, timeout=20)
        out += chunk

        bi = chunk.find(begin)
        ei = chunk.find(end)
        seg = ""
        if bi >= 0 and ei > bi:
            seg = chunk[bi + len(begin):ei]
        results.append({"command": command, "output": seg.strip()})

    send("exit\n")
    send("exit\n")
    time.sleep(0.2)
    proc.terminate()
    try:
        os.close(master_fd)
    except Exception:
        pass
    open(raw_out_path, "w").write(out)
    return {"raw_output": out, "results": results}
