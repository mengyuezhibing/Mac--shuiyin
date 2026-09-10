#!/usr/bin/env python3
"""App 原生窗口入口：pywebview(WKWebView) 包裹 Web UI。

- 双击 .app 打开独立原生窗口，不再弹出浏览器
- 关闭窗口即退出应用
- 顶部菜单栏已汉化为中文（pyobjc 重建 NSMenu）
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


def _start_server():
    from mac_wm.app import build_ui
    build_ui().queue(max_size=64).launch(
        server_name="127.0.0.1", server_port=PORT,
        show_error=True, inbrowser=False, prevent_thread_lock=True,
        css=".container{max-width:1080px;margin:auto} .footer{display:none !important} #footer{display:none !important}")


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


def setup_mac_menu():
    """用 pyobjc 将 macOS 菜单栏汉化为中文，并保留编辑/窗口快捷键。

    pywebview 的 func 在辅助线程调用，AppKit 修改必须回到主线程执行。
    """
    try:
        import AppKit
        import Foundation
        from AppKit import (NSApp, NSMenu, NSMenuItem,
                            NSCommandKeyMask, NSShiftKeyMask)
    except Exception as e:
        print("菜单汉化跳过(无法导入AppKit):", e)
        return

    if NSApp() is None:
        return

    def add_submenu(main, title, items):
        sub = NSMenu.alloc().initWithTitle_(title)
        for it in items:
            if it is None:
                sub.addItem_(NSMenuItem.separatorItem())
                continue
            t, action, key, shift = it
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                t, action, key)
            if key:
                mask = NSCommandKeyMask
                if shift:
                    mask |= NSShiftKeyMask
                mi.setKeyEquivalentModifierMask_(mask)
            sub.addItem_(mi)
        item = NSMenuItem.alloc().init()
        item.setSubmenu_(sub)
        main.addItem_(item)

    def build():
        try:
            app = NSApp()
            app.setApplicationName_("Mac 水印去除")
            main = NSMenu.alloc().init()
            # 应用菜单
            add_submenu(main, "Mac 水印去除", [
                ("关于 Mac 水印去除", "orderFrontStandardAboutPanel:", "", False),
                None,
                ("退出 Mac 水印去除", "terminate:", "q", False),
            ])
            # 编辑菜单（保留光标编辑快捷键）
            add_submenu(main, "编辑", [
                ("撤销", "undo:", "z", False),
                ("重做", "redo:", "z", True),
                None,
                ("剪切", "cut:", "x", False),
                ("拷贝", "copy:", "c", False),
                ("粘贴", "paste:", "v", False),
                ("删除", "delete:", "", False),
                ("全选", "selectAll:", "a", False),
            ])
            # 窗口菜单
            add_submenu(main, "窗口", [
                ("最小化", "performMiniature:", "m", False),
                ("缩放", "performZoom:", "", False),
                ("关闭窗口", "performClose:", "w", False),
                None,
                ("全部置于最前", "arrangeInFront:", "", False),
            ])
            app.setMainMenu_(main)
        except Exception as e:
            print("菜单构建失败:", e)

    # 调度到主线程执行 AppKit 修改
    Foundation.NSOperationQueue.mainQueue().addOperationWithBlock_(build)


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

    _wait_server()

    webview.create_window("Mac 水印去除", URL, width=1180, height=860,
                          min_size=(900, 640))
    webview.start(func=setup_mac_menu, gui="cocoa")
    os._exit(0)


if __name__ == "__main__":
    main()
