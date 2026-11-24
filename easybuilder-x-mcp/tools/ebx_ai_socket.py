# -*- coding: utf-8 -*-
"""EBX 本机 Screen View Socket 客户端（hoverwu / 0.1.0）。"""
import argparse
import glob
import json
import os
import socket
import sys


class EBXSocketError(RuntimeError):
    pass


def registry_files():
    base = os.path.join(os.environ.get("APPDATA", ""), "Weintek", "EasyBuilder X", "ai-sockets")
    return glob.glob(os.path.join(base, "*.json"))


def discover_instances(timeout=0.25):
    instances = []
    for path in registry_files():
        try:
            with open(path, encoding="utf-8") as f:
                item = json.load(f)
            if item.get("host") != "127.0.0.1" or not isinstance(item.get("port"), int):
                continue
            item["registry_file"] = path
            instances.append(item)
        except (OSError, ValueError):
            continue
    return sorted(instances, key=lambda x: x.get("started_at", ""), reverse=True)


class EBXSocket:
    def __init__(self, port=None, host="127.0.0.1", timeout=30):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _resolve_port(self):
        if self.port is not None:
            return self.port
        env_port = os.environ.get("EBX_AI_SOCKET_PORT")
        if env_port:
            return int(env_port)
        errors = []
        for item in discover_instances():
            candidate = EBXSocket(item["port"], self.host, min(self.timeout, 2))
            try:
                if candidate.call("ping").get("result") == "pong":
                    return item["port"]
            except (OSError, ValueError, EBXSocketError) as exc:
                errors.append(str(exc))
        detail = "; ".join(errors)
        raise EBXSocketError("没有可用的 EBX Socket 实例" + (": " + detail if detail else ""))

    def call(self, method, params=None):
        port = self._resolve_port()
        request = {
            "schema_version": "1.4",
            "method": method,
            "params": params if params is not None else {},
        }
        try:
            with socket.create_connection((self.host, port), self.timeout) as conn:
                conn.settimeout(self.timeout)
                conn.sendall(json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
                data = bytearray()
                while b"\n" not in data:
                    chunk = conn.recv(1048576)
                    if not chunk:
                        break
                    data.extend(chunk)
        except OSError as exc:
            raise EBXSocketError("连接 %s:%s 失败: %s" % (self.host, port, exc)) from exc
        try:
            response = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise EBXSocketError("EBX 返回了无效 JSON") from exc
        if not isinstance(response, dict):
            raise EBXSocketError("EBX 响应根节点不是对象")
        return response


def require_ok(response):
    if response.get("ok") is not True:
        error = response.get("error") or {}
        raise EBXSocketError("%s: %s" % (error.get("code", "EBX_ERROR"), error.get("message", response)))
    return response.get("result")


def main():
    parser = argparse.ArgumentParser(description="调用本机 EasyBuilder X Screen View Socket")
    parser.add_argument("command", choices=("list", "call"))
    parser.add_argument("method", nargs="?")
    parser.add_argument("params", nargs="?", default="{}")
    parser.add_argument("--port", type=int)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.command == "list":
        result = discover_instances()
    else:
        if not args.method:
            parser.error("call 需要 method")
        try:
            params = json.loads(args.params)
        except ValueError as exc:
            parser.error("params 不是有效 JSON: %s" % exc)
        result = EBXSocket(args.port).call(args.method, params)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EBXSocketError as exc:
        print("[ERR] %s" % exc, file=sys.stderr)
        sys.exit(1)
