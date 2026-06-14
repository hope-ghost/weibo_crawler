#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
路径工具模块
处理打包环境下的路径问题
"""

import os
import sys


def get_base_dir():
    """
    获取程序基础目录
    
    在打包环境中（如PyInstaller），返回可执行文件所在目录
    在开发环境中，返回脚本所在目录
    
    Returns:
        str: 程序基础目录的绝对路径
    """
    if getattr(sys, 'frozen', False):
        # 打包后的环境（PyInstaller等）
        # sys.executable 是可执行文件的路径
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # 开发环境
        # 返回脚本所在目录
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_path(relative_path):
    """
    获取资源文件的绝对路径
    
    在打包环境中，资源文件可能被打包到临时目录（_MEIPASS），
    需要先检查资源文件是否存在，如果不存在则使用相对路径
    
    Args:
        relative_path: 相对路径（相对于程序基础目录）
    
    Returns:
        str: 资源文件的绝对路径
    """
    base_dir = get_base_dir()
    
    # 如果是绝对路径，直接返回
    if os.path.isabs(relative_path):
        return relative_path
    
    # 尝试使用基础目录构建路径
    resource_path = os.path.join(base_dir, relative_path)
    
    # 如果文件不存在，尝试在打包环境的资源目录中查找
    if not os.path.exists(resource_path) and getattr(sys, 'frozen', False):
        # PyInstaller 会将资源打包到临时目录
        if hasattr(sys, '_MEIPASS'):
            meipass_path = os.path.join(sys._MEIPASS, relative_path)
            if os.path.exists(meipass_path):
                # 资源文件在临时目录中，但应该复制到可执行文件目录
                return resource_path
    
    return resource_path


def ensure_dir(dir_path):
    """
    确保目录存在，如果不存在则创建
    
    Args:
        dir_path: 目录路径（可以是相对路径或绝对路径）
    
    Returns:
        str: 创建的目录的绝对路径
    """
    if not os.path.isabs(dir_path):
        dir_path = os.path.join(get_base_dir(), dir_path)
    
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    
    return dir_path

