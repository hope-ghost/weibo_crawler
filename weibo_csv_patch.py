#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CSV补丁模块
用于修改CSV文件名格式，将文件名改为 _posts.csv 和 _comments.csv
"""

import weibo
import os


def apply_patch():
    """应用CSV补丁"""
    # 这个补丁模块主要用于关键词搜索，因为关键词搜索已经在keyword_search.py中
    # 使用了正确的文件名格式（_posts.csv 和 _comments.csv）
    # 这里只是占位符，确保GUI不会报错
    weibo.logger.info("CSV补丁已加载（关键词搜索模式使用标准文件名格式）")

