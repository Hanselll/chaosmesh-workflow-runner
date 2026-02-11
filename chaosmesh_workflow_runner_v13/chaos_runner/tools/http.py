# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error

def http_get_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.URLError as e:
        raise RuntimeError("HTTP GET failed: {} err={}".format(url, e))
    except ValueError:
        raise RuntimeError("HTTP response is not JSON: {}".format(url))
