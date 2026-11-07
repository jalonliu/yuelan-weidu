# -*- coding: utf-8 -*-
"""阅览围读 agent 插件入口：本插件只提供 dashboard API 后端，不注册工具/hook。"""


def register(ctx):  # noqa: ANN001 - 契约签名
    """无工具注册；书库服务由 dashboard/plugin_api.py 按需唤醒。"""
    return None
