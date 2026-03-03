# -*- coding: utf-8 -*-
import json
import socket
import urllib.error
import urllib.request

def http_get_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except socket.timeout:
        raise RuntimeError("HTTP GET timeout: {} timeout={}s".format(url, timeout))
    except TimeoutError:
        raise RuntimeError("HTTP GET timeout: {} timeout={}s".format(url, timeout))
    except urllib.error.URLError as e:
        raise RuntimeError("HTTP GET failed: {} err={}".format(url, e))
    except ValueError:
        raise RuntimeError("HTTP response is not JSON: {}".format(url))
