#!/usr/bin/env python3
"""App 原生窗口入口：pywebview(WKWebView) 包裹 Web UI。

- 双击 .app 打开独立原生窗口，不再弹出浏览器
- 关闭窗口即退出应用
- macOS 菜单栏/对话框通过 pywebview 官方 localization 汉化为中文
"""

import os
import sys
import socket
import threading
import time

# 让非 bundle 的 Python 进程在菜单栏显示中文名（AppKit 早期读取）
os.environ.setdefault("_NSApplicationName", "Mac 水印去除")

PORT = 7860
URL = f"http://127.0.0.1:{PORT}"

# pywebview 菜单/对话框中文映射（键见 webview/localization.py）
_WEBVIEW_ZH = {
    "global.quitConfirmation": "确定要退出吗？",
    "global.ok": "确定",
    "global.quit": "退出",
    "global.cancel": "取消",
    "global.saveFile": "保存文件",
    "cocoa.menu.about": "关于",
    "cocoa.menu.services": "服务",
    "cocoa.menu.view": "显示",
    "cocoa.menu.edit": "编辑",
    "cocoa.menu.hide": "隐藏",
    "cocoa.menu.hideOthers": "隐藏其他",
    "cocoa.menu.showAll": "全部显示",
    "cocoa.menu.quit": "退出",
    "cocoa.menu.fullscreen": "进入全屏",
    "cocoa.menu.cut": "剪切",
    "cocoa.menu.copy": "拷贝",
    "cocoa.menu.paste": "粘贴",
    "cocoa.menu.selectAll": "全选",
}


def _localize_webview():
    """覆盖 pywebview 默认英文菜单文本为中文。"""
    try:
        from webview.localization import original_localization
        original_localization.update(_WEBVIEW_ZH)
    except Exception as e:
        print("菜单汉化(localization)失败:", e)


def _set_process_name():
    """设置进程名，使菜单栏 App 名称显示为中文。"""
    try:
        from Foundation import NSProcessInfo
        NSProcessInfo.processInfo().setProcessName_("Mac 水印去除")
    except Exception as e:
        print("进程名设置失败:", e)


def _start_server():
    from mac_wm.app import build_ui, HIDE_SETTINGS_HEAD
    build_ui().queue(max_size=64).launch(
        server_name="127.0.0.1", server_port=PORT,
        show_error=True, inbrowser=False, prevent_thread_lock=True,
        css=".container{max-width:1080px;margin:auto} .footer{display:none !important} #footer{display:none !important}",
        run_history=False, head=HIDE_SETTINGS_HEAD)


def _wait_server(timeout: float = 60.0) -> bool:
    """轮询等待 HTTP 服务就绪。"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.4)
    return False


def main():
    # 服务线程（端口被占用说明已有实例，仅打开窗口复用）
    def serve():
        try:
            _start_server()
        except OSError:
            pass

    threading.Thread(target=serve, daemon=True).start()

    try:
        import webview
    except ImportError:
        from mac_wm.app import main as browser_main
        browser_main()
        return

    # 菜单/对话框中文 + 进程名中文（须在创建窗口前设置）
    _localize_webview()
    _set_process_name()

    _wait_server()

    webview.create_window("Mac 水印去除", URL, width=1180, height=860,
                          min_size=(900, 640))
    webview.start(_set_process_name, gui="cocoa")
    os._exit(0)


if __name__ == "__main__":
    main()
