#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微博爬虫可视化界面
提供友好的图形界面来配置和运行微博爬虫
"""

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from datetime import datetime
import weibo
import const
import weibo_patch
import weibo_csv_patch
from util.pathutil import get_base_dir, get_resource_path, ensure_dir


class WeiboCrawlerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("微博爬虫 - 可视化界面")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
        # 配置文件路径（使用绝对路径）
        self.config_file = get_resource_path("config.json")
        self.user_id_list_file = get_resource_path("user_id_list.txt")
        
        # 加载配置
        self.config = self.load_config()
        
        # 爬虫线程
        self.crawler_thread = None
        self.is_running = False
        self.crawler_exception = None
        self.stop_requested = False
        
        # 创建界面
        self.create_widgets()
        
        # 加载用户ID列表
        self.load_user_id_list()
        
        # 绑定窗口关闭事件，自动保存配置
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 创建默认配置
                default_config = {
                    "user_id_list": "user_id_list.txt",
                    "only_crawl_original": 0,
                    "since_date": 1,
                    "start_page": 1,
                    "page_weibo_count": 10,
                    "write_mode": ["csv"],
                    "original_pic_download": 1,
                    "retweet_pic_download": 0,
                    "original_video_download": 1,
                    "retweet_video_download": 0,
                    "original_live_photo_download": 1,
                    "retweet_live_photo_download": 0,
                    "download_comment": 1,
                    "comment_max_download_count": 100,
                    "download_repost": 1,
                    "repost_max_download_count": 100,
                    "user_id_as_folder_name": 0,
                    "remove_html_tag": 1,
                    "cookie": "your cookie"
                }
                self.save_config(default_config)
                return default_config
        except Exception as e:
            messagebox.showerror("错误", f"加载配置文件失败: {str(e)}")
            return {}
    
    def save_config(self, config=None):
        """保存配置文件"""
        if config is None:
            config = self.config
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {str(e)}")
            return False
    
    def load_user_id_list(self):
        """加载用户ID列表"""
        try:
            if os.path.exists(self.user_id_list_file):
                with open(self.user_id_list_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if hasattr(self, 'user_listbox'):
                        self.user_listbox.delete(0, tk.END)
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                self.user_listbox.insert(tk.END, line)
        except Exception as e:
            messagebox.showerror("错误", f"加载用户ID列表失败: {str(e)}")
    
    def save_user_id_list(self):
        """保存用户ID列表"""
        try:
            with open(self.user_id_list_file, 'w', encoding='utf-8') as f:
                if hasattr(self, 'user_listbox'):
                    for i in range(self.user_listbox.size()):
                        f.write(self.user_listbox.get(i) + '\n')
            return True
        except Exception as e:
            messagebox.showerror("错误", f"保存用户ID列表失败: {str(e)}")
            return False
    
    def create_widgets(self):
        """创建界面组件"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重 - 使窗口能够自适应大小
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # 主框架的列和行权重配置
        main_frame.columnconfigure(0, weight=0, minsize=420)  # 配置面板，设置最小宽度420px
        main_frame.columnconfigure(1, weight=1)  # 用户管理面板，可水平扩展
        main_frame.columnconfigure(2, weight=1)  # 日志面板，可水平扩展
        main_frame.rowconfigure(0, weight=1)     # 配置和用户面板行，可垂直扩展
        main_frame.rowconfigure(1, weight=1)     # 日志面板行，可垂直扩展
        main_frame.rowconfigure(2, weight=0)     # 控制面板行，固定高度
        
        # 创建左侧配置面板
        self.create_config_panel(main_frame)
        
        # 创建中间用户管理面板
        self.create_user_panel(main_frame)
        
        # 创建右侧日志面板
        self.create_log_panel(main_frame)
        
        # 创建底部控制按钮
        self.create_control_panel(main_frame)
        
        # 加载用户ID列表
        self.load_user_id_list()
        
        # 检查配置一致性：如果启用了评论/转发下载但没有SQLite，提示用户
        self.check_comment_config()
    
    def create_config_panel(self, parent):
        """创建配置面板"""
        # 创建外层容器框架
        config_outer_frame = ttk.Frame(parent)
        config_outer_frame.grid(row=0, column=0, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        config_outer_frame.columnconfigure(0, weight=1)
        config_outer_frame.rowconfigure(0, weight=1)
        
        # 创建可滚动的配置面板 - 设置初始宽度确保内容完整显示
        canvas = tk.Canvas(config_outer_frame, highlightthickness=0, width=450)
        scrollbar = ttk.Scrollbar(config_outer_frame, orient="vertical", command=canvas.yview)
        config_frame = ttk.LabelFrame(canvas, text="配置选项", padding="10")
        
        # 配置滚动区域
        scrollable_frame = config_frame
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        def update_scroll_region(event=None):
            """更新滚动区域并确保canvas窗口宽度正确"""
            canvas.update_idletasks()
            # 获取canvas的实际宽度
            canvas_width = canvas.winfo_width()
            if canvas_width > 1:  # 确保canvas已渲染
                # 设置canvas窗口的宽度与canvas相同
                canvas.itemconfig(canvas_window, width=canvas_width)
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        scrollable_frame.bind("<Configure>", update_scroll_region)
        
        # 配置canvas和scrollbar
        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 配置canvas列权重 - 允许canvas扩展
        config_outer_frame.columnconfigure(0, weight=1)
        
        # 配置列权重 - 确保内部元素可以正确扩展
        config_frame.columnconfigure(1, weight=1)
        
        # 当canvas大小改变时，更新内部窗口宽度
        def on_canvas_configure(event):
            canvas_width = event.width
            canvas.itemconfig(canvas_window, width=canvas_width)
        
        canvas.bind('<Configure>', on_canvas_configure)
        
        # 绑定鼠标滚轮事件
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind('<Enter>', _bind_mousewheel)
        canvas.bind('<Leave>', _unbind_mousewheel)
        
        # 保存引用以便后续使用
        self.config_frame = config_frame
        self.config_canvas = canvas
        self.config_canvas_window = canvas_window
        
        # 延迟更新滚动区域（在所有子组件创建后）
        self.update_scroll_region = update_scroll_region
        
        row = 0
        
        # 采集模式
        ttk.Label(config_frame, text="采集模式:").grid(row=row, column=0, sticky=tk.W, pady=5)
        crawl_mode = self.config.get("crawl_mode", "user")  # user: 用户模式, keyword: 关键词模式, topic: 话题模式, hot_search: 热搜模式, single_link: 单链接模式
        mode_map = {"user": "用户模式", "keyword": "关键词模式", "topic": "话题模式", "hot_search": "热搜模式", "single_link": "单链接模式"}
        self.crawl_mode = tk.StringVar(value=mode_map.get(crawl_mode, "用户模式"))
        mode_combo = ttk.Combobox(config_frame, textvariable=self.crawl_mode, values=["用户模式", "关键词模式", "话题模式", "热搜模式", "单链接模式"], 
                    state="readonly", width=15)
        mode_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        mode_combo.bind("<<ComboboxSelected>>", self.on_crawl_mode_changed)
        row += 1
        
        # 爬取类型（仅用户模式显示）
        self.crawl_type_frame = ttk.Frame(config_frame)
        self.crawl_type_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(self.crawl_type_frame, text="爬取类型:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.crawl_type = tk.StringVar(value="全部" if self.config.get("only_crawl_original", 0) == 0 else "仅原创")
        ttk.Combobox(self.crawl_type_frame, textvariable=self.crawl_type, values=["全部", "仅原创"], 
                    state="readonly", width=15).grid(row=0, column=1, sticky=tk.W)
        row += 1
        
        # 起始日期
        ttk.Label(config_frame, text="起始日期:").grid(row=row, column=0, sticky=tk.W, pady=5)
        since_date = self.config.get("since_date", 1)
        # 如果since_date是"1900-01-01"，表示爬取全部，显示为空
        if since_date == "1900-01-01" or str(since_date) == "1900-01-01":
            self.since_date = tk.StringVar(value="")
        elif isinstance(since_date, int):
            self.since_date = tk.StringVar(value=str(since_date) + "天前")
        else:
            self.since_date = tk.StringVar(value=str(since_date))
        date_entry_frame = ttk.Frame(config_frame)
        date_entry_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        ttk.Entry(date_entry_frame, textvariable=self.since_date, width=18).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(date_entry_frame, text="(留空=全部 | yyyy-mm-dd | 数字天数)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        row += 1
        
        # 结束日期（所有模式都支持）
        self.end_date_frame = ttk.Frame(config_frame)
        self.end_date_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(self.end_date_frame, text="结束日期:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        end_date = self.config.get("end_date", "")
        # 如果结束日期为空，默认显示今天的日期
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        self.end_date = tk.StringVar(value=end_date)
        end_date_entry_frame = ttk.Frame(self.end_date_frame)
        end_date_entry_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        end_date_entry_frame.columnconfigure(0, weight=1)
        ttk.Entry(end_date_entry_frame, textvariable=self.end_date, width=18).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(end_date_entry_frame, text="(留空=今天 | yyyy-mm-dd)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        row += 1
        
        # 起始页码
        ttk.Label(config_frame, text="起始页码:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.start_page = tk.StringVar(value=str(self.config.get("start_page", 1)))
        ttk.Entry(config_frame, textvariable=self.start_page, width=18).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # 每页微博数
        ttk.Label(config_frame, text="每页微博数:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.page_weibo_count = tk.StringVar(value=str(self.config.get("page_weibo_count", 10)))
        ttk.Entry(config_frame, textvariable=self.page_weibo_count, width=18).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # 保存格式
        ttk.Label(config_frame, text="保存格式:").grid(row=row, column=0, sticky=tk.W, pady=5)
        write_modes = self.config.get("write_mode", ["csv"])
        self.write_mode_csv = tk.BooleanVar(value="csv" in write_modes)
        self.write_mode_json = tk.BooleanVar(value="json" in write_modes)
        format_frame = ttk.Frame(config_frame)
        format_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        format_frame.columnconfigure(0, weight=1)
        format_check_frame = ttk.Frame(format_frame)
        format_check_frame.grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(format_check_frame, text="CSV", variable=self.write_mode_csv).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(format_check_frame, text="JSON", variable=self.write_mode_json).pack(side=tk.LEFT, padx=5)
        ttk.Label(format_frame, text="(CSV模式支持直接保存评论/转发)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        row += 1
        
        # 下载选项
        ttk.Label(config_frame, text="下载选项:").grid(row=row, column=0, sticky=tk.W, pady=5)
        download_frame = ttk.Frame(config_frame)
        download_frame.grid(row=row, column=1, sticky=tk.W, pady=5)
        
        self.original_pic = tk.BooleanVar(value=self.config.get("original_pic_download", 1) == 1)
        self.retweet_pic = tk.BooleanVar(value=self.config.get("retweet_pic_download", 0) == 1)
        self.original_video = tk.BooleanVar(value=self.config.get("original_video_download", 1) == 1)
        self.retweet_video = tk.BooleanVar(value=self.config.get("retweet_video_download", 0) == 1)
        
        ttk.Checkbutton(download_frame, text="原创图片", variable=self.original_pic).grid(row=0, column=0, padx=5)
        ttk.Checkbutton(download_frame, text="转发图片", variable=self.retweet_pic).grid(row=0, column=1, padx=5)
        ttk.Checkbutton(download_frame, text="原创视频", variable=self.original_video).grid(row=1, column=0, padx=5)
        ttk.Checkbutton(download_frame, text="转发视频", variable=self.retweet_video).grid(row=1, column=1, padx=5)
        row += 1
        
        # 评论和转发
        ttk.Label(config_frame, text="评论/转发:").grid(row=row, column=0, sticky=tk.W, pady=5)
        comment_frame = ttk.Frame(config_frame)
        comment_frame.grid(row=row, column=1, sticky=tk.W, pady=5)
        
        self.download_comment = tk.BooleanVar(value=self.config.get("download_comment", 1) == 1)
        self.download_repost = tk.BooleanVar(value=self.config.get("download_repost", 1) == 1)
        self.comment_max = tk.StringVar(value=str(self.config.get("comment_max_download_count", 100)))
        self.repost_max = tk.StringVar(value=str(self.config.get("repost_max_download_count", 100)))
        
        ttk.Checkbutton(comment_frame, text="下载评论", variable=self.download_comment).grid(row=0, column=0, padx=5)
        ttk.Checkbutton(comment_frame, text="下载转发", variable=self.download_repost).grid(row=0, column=1, padx=5)
        ttk.Label(comment_frame, text="最大数量:").grid(row=1, column=0, padx=5, sticky=tk.W)
        ttk.Entry(comment_frame, textvariable=self.comment_max, width=10).grid(row=1, column=1, padx=5, sticky=tk.W)
        ttk.Label(comment_frame, text="(总数量，包括子评论)", font=("", 8), foreground="gray").grid(row=2, column=0, columnspan=2, padx=5, sticky=tk.W, pady=(2, 0))
        ttk.Label(comment_frame, text="(CSV模式直接保存为CSV文件)", font=("", 8), foreground="gray").grid(row=3, column=0, columnspan=2, padx=5, sticky=tk.W, pady=(2, 0))
        row += 1
        
        # 关键词过滤（用户模式下，在用户微博中搜索关键词）
        self.keyword_filter_frame = ttk.Frame(config_frame)
        self.keyword_filter_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(self.keyword_filter_frame, text="关键词过滤:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        keyword_filter_inner = ttk.Frame(self.keyword_filter_frame)
        keyword_filter_inner.grid(row=0, column=1, sticky=(tk.W, tk.E))
        keyword_filter_inner.columnconfigure(0, weight=1)
        
        # 从config中读取query_list，如果是list则转换为逗号分隔的字符串
        query_list = self.config.get("query_list", [])
        if isinstance(query_list, list):
            query_list_str = ",".join(query_list) if query_list else ""
        elif isinstance(query_list, str):
            query_list_str = query_list
        else:
            query_list_str = ""
        
        self.keywords = tk.StringVar(value=query_list_str)
        ttk.Entry(keyword_filter_inner, textvariable=self.keywords, width=30).grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Label(keyword_filter_inner, text="(多个关键词用逗号分隔，留空=爬取全部)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Label(keyword_filter_inner, text="(需要设置Cookie才能使用)", 
                 font=("", 8), foreground="orange").grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        row += 1
        
        # 关键词模式专用配置
        self.keyword_mode_frame = ttk.LabelFrame(config_frame, text="关键词搜索配置", padding="5")
        self.keyword_mode_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.keyword_mode_frame.columnconfigure(1, weight=1)
        
        # 搜索关键词（关键词模式）
        ttk.Label(self.keyword_mode_frame, text="搜索关键词:").grid(row=0, column=0, sticky=tk.W, pady=5)
        keyword_search_frame = ttk.Frame(self.keyword_mode_frame)
        keyword_search_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        keyword_search_frame.columnconfigure(0, weight=1)
        
        search_keywords = self.config.get("search_keywords", "")
        if isinstance(search_keywords, list):
            search_keywords = ",".join(search_keywords) if search_keywords else ""
        self.search_keywords = tk.StringVar(value=search_keywords)
        ttk.Entry(keyword_search_frame, textvariable=self.search_keywords, width=30).grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Label(keyword_search_frame, text="(多个关键词用逗号分隔，必填)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Label(keyword_search_frame, text="(需要设置Cookie才能使用)", 
                 font=("", 8), foreground="orange").grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        
        # 最大搜索条数（关键词模式）
        ttk.Label(self.keyword_mode_frame, text="最大搜索条数:").grid(row=1, column=0, sticky=tk.W, pady=5)
        max_count_frame = ttk.Frame(self.keyword_mode_frame)
        max_count_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)
        max_count_frame.columnconfigure(0, weight=1)
        self.max_search_count = tk.StringVar(value=str(self.config.get("max_search_count", 100)))
        ttk.Entry(max_count_frame, textvariable=self.max_search_count, width=18).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(max_count_frame, text="(限制搜索结果的微博数量)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        
        row += 1
        
        # 话题模式专用配置
        self.topic_mode_frame = ttk.LabelFrame(config_frame, text="话题搜索配置", padding="5")
        self.topic_mode_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.topic_mode_frame.columnconfigure(1, weight=1)
        
        # 搜索话题（话题模式）
        ttk.Label(self.topic_mode_frame, text="搜索话题:").grid(row=0, column=0, sticky=tk.W, pady=5)
        topic_search_frame = ttk.Frame(self.topic_mode_frame)
        topic_search_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        topic_search_frame.columnconfigure(0, weight=1)
        
        search_topics = self.config.get("search_topics", "")
        if isinstance(search_topics, list):
            search_topics = ",".join(search_topics) if search_topics else ""
        self.search_topics = tk.StringVar(value=search_topics)
        ttk.Entry(topic_search_frame, textvariable=self.search_topics, width=30).grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Label(topic_search_frame, text="(多个话题用逗号分隔，可带#号或不带，必填)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Label(topic_search_frame, text="(需要设置Cookie才能使用)", 
                 font=("", 8), foreground="orange").grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        
        # 最大搜索条数（话题模式）
        ttk.Label(self.topic_mode_frame, text="最大搜索条数:").grid(row=1, column=0, sticky=tk.W, pady=5)
        max_topic_count_frame = ttk.Frame(self.topic_mode_frame)
        max_topic_count_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)
        max_topic_count_frame.columnconfigure(0, weight=1)
        self.max_topic_search_count = tk.StringVar(value=str(self.config.get("max_topic_search_count", 100)))
        ttk.Entry(max_topic_count_frame, textvariable=self.max_topic_search_count, width=18).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(max_topic_count_frame, text="(限制搜索结果的微博数量)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        
        row += 1
        
        # 热搜模式专用配置
        self.hot_search_mode_frame = ttk.LabelFrame(config_frame, text="热搜模式配置", padding="5")
        self.hot_search_mode_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.hot_search_mode_frame.columnconfigure(1, weight=1)
        
        # 是否使用所有热搜话题
        self.use_all_hot_topics = tk.BooleanVar(value=self.config.get("use_all_hot_topics", True))
        ttk.Checkbutton(self.hot_search_mode_frame, text="采集所有热搜话题", variable=self.use_all_hot_topics,
                       command=self.on_hot_search_mode_changed).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # 最大热搜话题数
        ttk.Label(self.hot_search_mode_frame, text="最大热搜话题数:").grid(row=1, column=0, sticky=tk.W, pady=5)
        max_hot_topics_frame = ttk.Frame(self.hot_search_mode_frame)
        max_hot_topics_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)
        max_hot_topics_frame.columnconfigure(0, weight=1)
        self.max_hot_topics = tk.StringVar(value=str(self.config.get("max_hot_topics", 50)))
        ttk.Entry(max_hot_topics_frame, textvariable=self.max_hot_topics, width=18).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(max_hot_topics_frame, text="(默认前50个热搜)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        
        # 每个话题默认采集数量
        ttk.Label(self.hot_search_mode_frame, text="每个话题默认采集数:").grid(row=2, column=0, sticky=tk.W, pady=5)
        posts_per_topic_frame = ttk.Frame(self.hot_search_mode_frame)
        posts_per_topic_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        posts_per_topic_frame.columnconfigure(0, weight=1)
        self.posts_per_hot_topic = tk.StringVar(value=str(self.config.get("posts_per_hot_topic", 100)))
        ttk.Entry(posts_per_topic_frame, textvariable=self.posts_per_hot_topic, width=18).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(posts_per_topic_frame, text="(每个热搜话题默认采集的微博数量)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        
        # 选择特定热搜话题
        selected_topics_frame = ttk.Frame(self.hot_search_mode_frame)
        selected_topics_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        selected_topics_frame.columnconfigure(1, weight=1)
        ttk.Label(selected_topics_frame, text="选择特定话题:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        
        selected_topics_inner = ttk.Frame(selected_topics_frame)
        selected_topics_inner.grid(row=0, column=1, sticky=(tk.W, tk.E))
        selected_topics_inner.columnconfigure(0, weight=1)
        
        selected_topics = self.config.get("selected_hot_topics", [])
        if isinstance(selected_topics, list):
            selected_topics_str = ",".join(selected_topics) if selected_topics else ""
        else:
            selected_topics_str = str(selected_topics) if selected_topics else ""
        self.selected_hot_topics = tk.StringVar(value=selected_topics_str)
        ttk.Entry(selected_topics_inner, textvariable=self.selected_hot_topics, width=30).grid(row=0, column=0, sticky=(tk.W, tk.E))
        ttk.Label(selected_topics_inner, text="(留空=使用所有热搜 | 多个话题用逗号分隔，如: 话题1,话题2)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Label(selected_topics_inner, text="(需要设置Cookie才能使用)", 
                 font=("", 8), foreground="orange").grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        
        ttk.Button(selected_topics_frame, text="刷新热搜榜", command=self.refresh_hot_search_list).grid(row=0, column=2, padx=5)
        
        row += 1
        
        # 单链接模式专用配置
        self.single_link_mode_frame = ttk.LabelFrame(config_frame, text="单链接爬取配置", padding="5")
        self.single_link_mode_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.single_link_mode_frame.columnconfigure(1, weight=1)
        
        # 微博链接输入（单链接模式）
        ttk.Label(self.single_link_mode_frame, text="微博链接:").grid(row=0, column=0, sticky=tk.W, pady=5)
        single_link_frame = ttk.Frame(self.single_link_mode_frame)
        single_link_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        single_link_frame.columnconfigure(0, weight=1)
        
        weibo_url = self.config.get("weibo_url", "")
        self.weibo_url = tk.StringVar(value=weibo_url)
        ttk.Entry(single_link_frame, textvariable=self.weibo_url, width=30).grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Label(single_link_frame, text="(支持weibo.com或m.weibo.cn链接，必填)", 
                 font=("", 8), foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Label(single_link_frame, text="(需要设置Cookie才能使用)", 
                 font=("", 8), foreground="orange").grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        
        row += 1
        
        # 初始化时根据模式显示/隐藏相关配置
        self.on_crawl_mode_changed()
        
        # Cookie设置
        ttk.Label(config_frame, text="Cookie:").grid(row=row, column=0, sticky=tk.W, pady=5)
        cookie_frame = ttk.Frame(config_frame)
        cookie_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        cookie_frame.columnconfigure(0, weight=1)
        
        # Cookie输入框 - 不设置固定width，让它自适应
        self.cookie_text = scrolledtext.ScrolledText(cookie_frame, height=3)
        self.cookie_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.cookie_text.insert("1.0", self.config.get("cookie", "your cookie"))
        
        ttk.Button(cookie_frame, text="验证Cookie", command=self.check_cookie).grid(row=1, column=0, pady=5)
        row += 1
        
        # 更新滚动区域（在所有配置项创建完成后）
        def finalize_config_panel():
            """最终确定配置面板的布局和滚动区域"""
            if hasattr(self, 'update_scroll_region'):
                self.update_scroll_region()
                # 确保canvas窗口宽度正确
                canvas_width = self.config_canvas.winfo_width()
                if canvas_width > 1:
                    self.config_canvas.itemconfig(self.config_canvas_window, width=canvas_width)
        
        self.root.after(200, finalize_config_panel)  # 延迟更新，确保所有组件都已布局
    
    def create_user_panel(self, parent):
        """创建用户管理面板"""
        user_frame = ttk.LabelFrame(parent, text="用户ID管理", padding="10")
        user_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        user_frame.columnconfigure(0, weight=1)
        user_frame.rowconfigure(1, weight=1)  # 用户列表区域可扩展
        
        # 用户ID输入框
        input_frame = ttk.Frame(user_frame)
        input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        input_frame.columnconfigure(0, weight=1)
        
        ttk.Label(input_frame, text="用户ID:").grid(row=0, column=0, sticky=tk.W)
        self.user_id_entry = ttk.Entry(input_frame)
        self.user_id_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        self.user_id_entry.bind('<Return>', lambda e: self.add_user())
        ttk.Label(input_frame, text="格式: user_id 或 user_id 昵称 或 user_id 昵称 日期", 
                 font=("", 8), foreground="gray").grid(row=2, column=0, sticky=tk.W, pady=2)
        
        # 用户列表
        list_frame = ttk.Frame(user_frame)
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.user_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        self.user_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.user_listbox.yview)
        
        # 用户操作按钮 - 使用grid布局，设置2列实现自动换行
        button_frame = ttk.Frame(user_frame)
        button_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        # 设置2列，让按钮能够自动换行
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        
        # 所有按钮使用grid布局，会自动换行
        ttk.Button(button_frame, text="添加", command=self.add_user).grid(row=0, column=0, sticky=(tk.W, tk.E), padx=2, pady=2)
        ttk.Button(button_frame, text="删除", command=self.delete_user).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=2, pady=2)
        ttk.Button(button_frame, text="清空", command=self.clear_users).grid(row=1, column=0, sticky=(tk.W, tk.E), padx=2, pady=2)
        ttk.Button(button_frame, text="从文件导入", command=self.import_users).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=2, pady=2)
    
    def create_log_panel(self, parent):
        """创建日志面板"""
        log_frame = ttk.LabelFrame(parent, text="运行日志", padding="10")
        log_frame.grid(row=0, column=2, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)  # 日志文本框可扩展
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, width=40, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 清空日志按钮
        ttk.Button(log_frame, text="清空日志", command=self.clear_log).grid(row=1, column=0, pady=5)
    
    def create_control_panel(self, parent):
        """创建控制面板"""
        control_frame = ttk.Frame(parent)
        control_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=10)
        control_frame.columnconfigure(0, weight=1)
        
        # 状态标签
        self.status_label = ttk.Label(control_frame, text="状态: 就绪", font=("", 10, "bold"))
        self.status_label.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        
        # 控制按钮 - 使用grid布局，设置2列实现自动换行
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        # 设置2列，让按钮能够自动换行
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        
        self.start_button = ttk.Button(button_frame, text="开始爬取", command=self.start_crawl)
        self.start_button.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=2, pady=2)
        
        self.stop_button = ttk.Button(button_frame, text="停止爬取", command=self.stop_crawl, 
                                      state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=2, pady=2)
        
        ttk.Button(button_frame, text="打开结果文件夹", command=self.open_result_folder).grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=2, pady=2)
    
    def log(self, message, level="INFO"):
        """添加日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def clear_log(self):
        """清空日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def save_all_config(self):
        """保存所有配置"""
        try:
            # 更新配置字典
            self.config["only_crawl_original"] = 0 if self.crawl_type.get() == "全部" else 1
            
            # 处理起始日期
            since_date_str = self.since_date.get().strip()
            if not since_date_str:
                # 如果为空，设置为"1900-01-01"表示爬取全部
                self.config["since_date"] = "1900-01-01"
            elif since_date_str.endswith("天前"):
                # 如果以"天前"结尾，提取数字
                try:
                    days = int(since_date_str.replace("天前", "").strip())
                    self.config["since_date"] = days
                except:
                    self.config["since_date"] = since_date_str
            elif since_date_str.isdigit():
                # 如果是纯数字，转换为整数（表示天数）
                try:
                    self.config["since_date"] = int(since_date_str)
                except:
                    self.config["since_date"] = since_date_str
            else:
                # 否则作为日期字符串保存
                self.config["since_date"] = since_date_str
            
            # 处理结束日期（所有模式都支持）
            end_date_str = self.end_date.get().strip()
            if not end_date_str:
                # 如果为空，默认设置为今天的日期
                self.config["end_date"] = datetime.now().strftime("%Y-%m-%d")
            else:
                # 验证日期格式
                try:
                    datetime.strptime(end_date_str, "%Y-%m-%d")
                    self.config["end_date"] = end_date_str
                except ValueError:
                    # 如果日期格式不正确，使用今天
                    self.log(f"结束日期格式不正确: {end_date_str}，使用今天作为结束日期", "WARNING")
                    self.config["end_date"] = datetime.now().strftime("%Y-%m-%d")
            
            self.config["start_page"] = int(self.start_page.get())
            self.config["page_weibo_count"] = int(self.page_weibo_count.get())
            
            # 保存格式
            write_modes = []
            if self.write_mode_csv.get():
                write_modes.append("csv")
            if self.write_mode_json.get():
                write_modes.append("json")
            self.config["write_mode"] = write_modes if write_modes else ["csv"]
            
            # 下载选项
            self.config["original_pic_download"] = 1 if self.original_pic.get() else 0
            self.config["retweet_pic_download"] = 1 if self.retweet_pic.get() else 0
            self.config["original_video_download"] = 1 if self.original_video.get() else 0
            self.config["retweet_video_download"] = 1 if self.retweet_video.get() else 0
            
            # 评论和转发
            self.config["download_comment"] = 1 if self.download_comment.get() else 0
            self.config["download_repost"] = 1 if self.download_repost.get() else 0
            self.config["comment_max_download_count"] = int(self.comment_max.get())
            self.config["repost_max_download_count"] = int(self.repost_max.get())
            
            # 采集模式
            mode = self.crawl_mode.get()
            if mode == "用户模式":
                self.config["crawl_mode"] = "user"
            elif mode == "关键词模式":
                self.config["crawl_mode"] = "keyword"
            elif mode == "话题模式":
                self.config["crawl_mode"] = "topic"
            elif mode == "热搜模式":
                self.config["crawl_mode"] = "hot_search"
            elif mode == "单链接模式":
                self.config["crawl_mode"] = "single_link"
            
            # 关键词过滤（用户模式下，在用户微博中搜索关键词）
            keywords_str = self.keywords.get().strip()
            if keywords_str:
                # 将逗号分隔的字符串转换为list，并去除空白
                query_list = [kw.strip() for kw in keywords_str.split(",") if kw.strip()]
                self.config["query_list"] = query_list
            else:
                # 如果为空，设置为空list
                self.config["query_list"] = []
            
            # 关键词搜索（关键词模式）
            if mode == "关键词模式":
                search_keywords_str = self.search_keywords.get().strip()
                if search_keywords_str:
                    search_keywords_list = [kw.strip() for kw in search_keywords_str.split(",") if kw.strip()]
                    self.config["search_keywords"] = search_keywords_list
                else:
                    self.config["search_keywords"] = []
            
            # 话题搜索（话题模式）
            if mode == "话题模式":
                search_topics_str = self.search_topics.get().strip()
                if search_topics_str:
                    search_topics_list = [t.strip() for t in search_topics_str.split(",") if t.strip()]
                    self.config["search_topics"] = search_topics_list
                else:
                    self.config["search_topics"] = []
            
            # 最大搜索条数（关键词模式）
            if mode == "关键词模式":
                try:
                    self.config["max_search_count"] = int(self.max_search_count.get())
                except:
                    self.config["max_search_count"] = 100
            
            # 最大搜索条数（话题模式）
            if mode == "话题模式":
                try:
                    self.config["max_topic_search_count"] = int(self.max_topic_search_count.get())
                except:
                    self.config["max_topic_search_count"] = 100
            
            # 热搜模式配置
            if mode == "热搜模式":
                try:
                    self.config["max_hot_topics"] = int(self.max_hot_topics.get())
                except:
                    self.config["max_hot_topics"] = 50
                
                try:
                    self.config["posts_per_hot_topic"] = int(self.posts_per_hot_topic.get())
                except:
                    self.config["posts_per_hot_topic"] = 100
                
                self.config["use_all_hot_topics"] = self.use_all_hot_topics.get()
                
                selected_topics_str = self.selected_hot_topics.get().strip()
                if selected_topics_str:
                    selected_topics_list = [t.strip() for t in selected_topics_str.split(",") if t.strip()]
                    self.config["selected_hot_topics"] = selected_topics_list
                else:
                    self.config["selected_hot_topics"] = []
            
            # 单链接模式配置
            if mode == "单链接模式":
                weibo_url_str = self.weibo_url.get().strip()
                self.config["weibo_url"] = weibo_url_str
            
            # Cookie
            self.config["cookie"] = self.cookie_text.get("1.0", tk.END).strip()
            
            # 保存配置
            if self.save_config():
                self.log("配置保存成功")
                messagebox.showinfo("成功", "配置已保存")
            else:
                self.log("配置保存失败", "ERROR")
        except Exception as e:
            self.log(f"保存配置时出错: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")
    
    def add_user(self):
        """添加用户ID"""
        user_id = self.user_id_entry.get().strip()
        if user_id:
            # 支持格式: user_id 或 user_id 昵称 或 user_id 昵称 日期
            parts = user_id.split()
            if parts and parts[0].isdigit():
                # 检查是否已存在
                existing_ids = [self.user_listbox.get(i).split()[0] for i in range(self.user_listbox.size())]
                if parts[0] in existing_ids:
                    if not messagebox.askyesno("确认", f"用户ID {parts[0]} 已存在，是否替换？"):
                        return
                    # 删除已存在的
                    for i in range(self.user_listbox.size()):
                        if self.user_listbox.get(i).split()[0] == parts[0]:
                            self.user_listbox.delete(i)
                            break
                
                self.user_listbox.insert(tk.END, user_id)
                self.user_id_entry.delete(0, tk.END)
                self.log(f"添加用户ID: {user_id}")
                # 自动保存用户ID列表
                self.save_user_id_list()
            else:
                messagebox.showwarning("警告", "用户ID必须是数字\n格式: user_id 或 user_id 昵称 或 user_id 昵称 日期")
        else:
            messagebox.showwarning("警告", "请输入用户ID")
    
    def delete_user(self):
        """删除选中的用户ID"""
        selection = self.user_listbox.curselection()
        if selection:
            user_id = self.user_listbox.get(selection[0])
            self.user_listbox.delete(selection[0])
            self.log(f"删除用户ID: {user_id}")
            # 自动保存用户ID列表
            self.save_user_id_list()
        else:
            messagebox.showwarning("警告", "请先选择要删除的用户ID")
    
    def clear_users(self):
        """清空用户列表"""
        if messagebox.askyesno("确认", "确定要清空所有用户ID吗？"):
            self.user_listbox.delete(0, tk.END)
            self.log("已清空用户列表")
            # 自动保存用户ID列表
            self.save_user_id_list()
    
    def import_users(self):
        """从文件导入用户ID"""
        file_path = filedialog.askopenfilename(
            title="选择用户ID文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    count = 0
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split()
                            if parts and parts[0].isdigit():
                                self.user_listbox.insert(tk.END, line)
                                count += 1
                    self.log(f"从文件导入 {count} 个用户ID")
                    # 自动保存用户ID列表
                    self.save_user_id_list()
                    messagebox.showinfo("成功", f"成功导入 {count} 个用户ID")
            except Exception as e:
                self.log(f"导入用户ID失败: {str(e)}", "ERROR")
                messagebox.showerror("错误", f"导入失败: {str(e)}")
    
    def check_cookie(self):
        """验证Cookie有效性"""
        cookie = self.cookie_text.get("1.0", tk.END).strip()
        if not cookie or cookie == "your cookie":
            messagebox.showwarning("警告", "请先输入Cookie")
            return
        
        self.log("正在验证Cookie...")
        
        # 在新线程中验证Cookie，避免阻塞UI
        def verify_cookie():
            try:
                import requests
                
                # 创建会话
                session = requests.Session()
                
                # 解析Cookie字符串
                cookies_dict = {}
                for item in cookie.split(';'):
                    item = item.strip()
                    if '=' in item:
                        key, value = item.split('=', 1)
                        cookies_dict[key.strip()] = value.strip()
                
                # 检查Cookie中是否包含SUB字段（这是必需的）
                if 'SUB' not in cookies_dict:
                    self.root.after(0, lambda: self.on_cookie_verified(False, "Cookie缺少SUB字段，这是必需的\n请确保Cookie中包含SUB字段"))
                    return
                
                # 设置Cookie
                session.cookies.update(cookies_dict)
                
                # 设置请求头（模拟浏览器）
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                    'Referer': 'https://m.weibo.cn/',
                    'MWeibo-Pwa': '1',
                    'X-Requested-With': 'XMLHttpRequest',
                }
                
                # 方法1：尝试访问需要登录的API - 获取当前登录用户的信息
                # 使用一个公开的测试用户ID来验证Cookie是否有效
                test_user_id = "1191965271"  # 微博官方账号，用于测试
                test_url = "https://m.weibo.cn/api/container/getIndex"
                params = {
                    'type': 'uid',
                    'value': test_user_id,
                    'containerid': f'100505{test_user_id}'
                }
                
                try:
                    response = session.get(test_url, params=params, headers=headers, timeout=10)
                    
                    # 检查响应状态码
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            # 如果返回了ok=1且有data，说明Cookie有效
                            if data.get('ok') == 1 and 'data' in data:
                                # 尝试获取当前登录用户信息
                                # 访问用户信息API
                                user_info_url = "https://m.weibo.cn/api/container/getIndex"
                                user_params = {
                                    'type': 'uid',
                                    'value': test_user_id
                                }
                                user_response = session.get(user_info_url, params=user_params, headers=headers, timeout=10)
                                
                                if user_response.status_code == 200:
                                    user_data = user_response.json()
                                    if user_data.get('ok') == 1:
                                        # Cookie有效，尝试获取当前登录用户信息
                                        # 访问一个需要登录的API来验证
                                        # 尝试获取用户卡片信息（需要登录）
                                        card_data = data.get('data', {})
                                        if card_data:
                                            # 尝试从返回的数据中获取用户信息
                                            user_info = card_data.get('userInfo', {})
                                            if user_info:
                                                screen_name = user_info.get('screen_name', '')
                                                if screen_name:
                                                    self.root.after(0, lambda name=screen_name: self.on_cookie_verified(True, f"Cookie有效！\n已成功访问需要登录的API\n测试用户: {name}"))
                                                    return
                                        
                                        # 如果无法获取用户名，至少确认Cookie有效
                                        self.root.after(0, lambda: self.on_cookie_verified(True, "Cookie有效！\n已成功访问需要登录的API"))
                                        return
                        except Exception as e:
                            # JSON解析失败，可能是HTML页面（说明被重定向到登录页）
                            response_text = response.text[:500] if response.text else ""
                            if '登录' in response_text or 'login' in response_text.lower() or 'captcha' in response_text.lower() or '验证' in response_text:
                                self.root.after(0, lambda: self.on_cookie_verified(False, "Cookie无效或已过期\n检测到登录页面，请重新获取Cookie"))
                                return
                    elif response.status_code == 403:
                        self.root.after(0, lambda: self.on_cookie_verified(False, "Cookie无效或已过期\n访问被禁止(403)，请重新获取Cookie"))
                        return
                    elif response.status_code == 418:
                        self.root.after(0, lambda: self.on_cookie_verified(False, "Cookie可能无效\n请求被识别为机器人(418)，请检查Cookie是否正确"))
                        return
                    else:
                        # 其他状态码，尝试检查响应内容
                        response_text = response.text[:500] if response.text else ""
                        if '登录' in response_text or 'login' in response_text.lower():
                            self.root.after(0, lambda: self.on_cookie_verified(False, f"Cookie无效或已过期\nHTTP状态码: {response.status_code}，检测到登录页面"))
                            return
                except requests.exceptions.Timeout:
                    self.root.after(0, lambda: self.on_cookie_verified(False, "验证超时，请检查网络连接"))
                    return
                except requests.exceptions.RequestException as e:
                    self.root.after(0, lambda: self.on_cookie_verified(False, f"验证失败: {str(e)}"))
                    return
                
                # 如果上面的方法都失败了，说明Cookie可能无效
                self.root.after(0, lambda: self.on_cookie_verified(False, "Cookie验证失败\n无法访问需要登录的API，请检查Cookie是否正确或已过期"))
                    
            except Exception as e:
                self.root.after(0, lambda: self.on_cookie_verified(False, f"验证出错: {str(e)}"))
        
        # 在新线程中运行验证
        import threading
        threading.Thread(target=verify_cookie, daemon=True).start()
    
    def on_cookie_verified(self, is_valid, message):
        """Cookie验证完成后的回调"""
        if is_valid:
            self.log(f"Cookie验证成功: {message}")
            messagebox.showinfo("验证成功", message)
        else:
            self.log(f"Cookie验证失败: {message}", "WARNING")
            messagebox.showwarning("验证失败", message)
    
    def start_crawl(self):
        """开始爬取"""
        if self.is_running:
            messagebox.showwarning("警告", "爬取任务正在运行中")
            return
        
        # 根据采集模式进行不同的检查
        mode = self.crawl_mode.get()
        if mode == "用户模式":
            # 用户模式：检查用户列表
            if self.user_listbox.size() == 0:
                messagebox.showwarning("警告", "请先添加要爬取的用户ID")
                return
        elif mode == "关键词模式":
            # 关键词模式：检查关键词
            search_keywords = self.search_keywords.get().strip()
            if not search_keywords:
                messagebox.showwarning("警告", "请输入搜索关键词")
                return
        elif mode == "话题模式":
            # 话题模式：检查话题
            search_topics = self.search_topics.get().strip()
            if not search_topics:
                messagebox.showwarning("警告", "请输入搜索话题")
                return
        elif mode == "热搜模式":
            # 热搜模式：检查Cookie（必须）
            cookie = self.cookie_text.get("1.0", tk.END).strip()
            if not cookie or cookie == "your cookie":
                if not messagebox.askyesno("警告", "热搜模式必须设置Cookie才能使用\n是否继续？"):
                    return
        elif mode == "单链接模式":
            # 单链接模式：检查链接
            weibo_url = self.weibo_url.get().strip()
            if not weibo_url:
                messagebox.showwarning("警告", "请输入微博链接")
                return
            # 检查Cookie（建议）
            cookie = self.cookie_text.get("1.0", tk.END).strip()
            if not cookie or cookie == "your cookie":
                if not messagebox.askyesno("警告", "单链接模式建议设置Cookie才能正常使用\n是否继续？"):
                    return
        
        # 保存配置（必须在获取模式之前保存，确保配置已更新）
        self.save_all_config()
        
        # 重新获取模式（从config中获取，确保是最新的）
        mode = self.config.get("crawl_mode", "user")
        mode_display = self.crawl_mode.get()  # 用于显示和检查
        
        # 根据模式进行不同的处理（使用mode_display进行判断，因为这是GUI控件的值）
        if mode_display == "用户模式":
            # 用户模式：保存用户ID列表到文件
            if not self.save_user_id_list():
                return
        elif mode_display == "关键词模式":
            # 关键词模式：不需要用户ID列表，但需要检查Cookie
            cookie = self.config.get("cookie", "").strip()
            if not cookie or cookie == "your cookie":
                if not messagebox.askyesno("警告", "关键词搜索需要设置Cookie才能使用\n是否继续？"):
                    return
        elif mode_display == "话题模式":
            # 话题模式：不需要用户ID列表，但需要检查Cookie
            cookie = self.config.get("cookie", "").strip()
            if not cookie or cookie == "your cookie":
                if not messagebox.askyesno("警告", "话题搜索需要设置Cookie才能使用\n是否继续？"):
                    return
        elif mode_display == "单链接模式":
            # 单链接模式：不需要用户ID列表，但建议检查Cookie
            cookie = self.config.get("cookie", "").strip()
            if not cookie or cookie == "your cookie":
                if not messagebox.askyesno("警告", "单链接模式建议设置Cookie才能正常使用\n是否继续？"):
                    return
        
        # 确保结果文件夹存在
        result_folder = os.path.join(get_base_dir(), "weibo")
        try:
            ensure_dir(result_folder)
            self.log(f"结果文件夹: {result_folder}")
        except Exception as e:
            self.log(f"创建结果文件夹失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"无法创建结果文件夹: {str(e)}")
            return
        
        # 根据模式显示不同的日志信息（使用保存后的配置）
        mode_from_config = self.config.get("crawl_mode", "user")
        self.log("=" * 50)
        if mode_from_config == "single_link":
            # 单链接模式
            weibo_url = self.config.get("weibo_url", "")
            self.log("开始单链接爬取")
            self.log(f"微博链接: {weibo_url}")
            if not self.config.get("cookie", "").strip():
                self.log("警告: 单链接模式建议设置Cookie，否则可能无法正常工作", "WARNING")
        elif mode == "keyword":
            # 关键词模式
            search_keywords = self.config.get("search_keywords", [])
            max_count = self.config.get("max_search_count", 100)
            self.log("开始关键词搜索")
            self.log(f"搜索关键词: {', '.join(search_keywords) if search_keywords else '无'}")
            self.log(f"最大搜索条数: {max_count}")
            if not self.config.get("cookie", "").strip():
                self.log("警告: 关键词搜索需要设置Cookie，否则可能无法正常工作", "WARNING")
        elif mode == "topic":
            # 话题模式
            search_topics = self.config.get("search_topics", [])
            max_count = self.config.get("max_topic_search_count", 100)
            self.log("开始话题搜索")
            self.log(f"搜索话题: {', '.join(search_topics) if search_topics else '无'}")
            self.log(f"最大搜索条数: {max_count}")
            if not self.config.get("cookie", "").strip():
                self.log("警告: 话题搜索需要设置Cookie，否则可能无法正常工作", "WARNING")
        elif mode == "hot_search":
            # 热搜模式
            max_topics = self.config.get("max_hot_topics", 50)
            posts_per_topic = self.config.get("posts_per_hot_topic", 100)
            use_all = self.config.get("use_all_hot_topics", True)
            selected_topics = self.config.get("selected_hot_topics", [])
            self.log("开始热搜模式采集")
            self.log(f"最大热搜话题数: {max_topics}")
            self.log(f"每个话题默认采集数: {posts_per_topic}")
            if use_all:
                self.log("将采集所有热搜话题")
            else:
                self.log(f"将采集选定的 {len(selected_topics)} 个话题: {', '.join(selected_topics[:5])}")
                if len(selected_topics) > 5:
                    self.log(f"  ... 还有 {len(selected_topics) - 5} 个话题")
            if not self.config.get("cookie", "").strip():
                self.log("警告: 热搜模式必须设置Cookie，否则无法正常工作", "WARNING")
        else:
            # 用户模式
            user_ids = []
            for i in range(self.user_listbox.size()):
                line = self.user_listbox.get(i).strip()
                if line:
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        user_ids.append(parts[0])
            
            # 更新配置中的user_id_list为文件路径
            self.config["user_id_list"] = self.user_id_list_file
            self.save_config()
            
            self.log("开始爬取微博")
            self.log(f"用户ID列表: {', '.join(user_ids)}")
            # 显示起始日期信息
            since_date_value = self.config.get("since_date", "")
            if since_date_value == "1900-01-01":
                self.log("起始日期: 全部（从最新开始往前爬取所有）")
            elif isinstance(since_date_value, int):
                self.log(f"起始日期: 最近{since_date_value}天")
            else:
                self.log(f"起始日期: {since_date_value}")
            # 显示结束日期信息
            end_date_value = self.config.get("end_date", "")
            if end_date_value:
                self.log(f"结束日期: {end_date_value}")
            # 显示关键词过滤信息
            query_list = self.config.get("query_list", [])
            if query_list and len(query_list) > 0:
                self.log(f"关键词过滤: {', '.join(query_list)}")
                if not self.config.get("cookie", "").strip():
                    self.log("警告: 关键词过滤需要设置Cookie，否则可能无法正常工作", "WARNING")
            else:
                self.log("关键词过滤: 无（爬取全部微博）")
        
        self.log("提示: 数据将每页自动保存，可随时安全停止")
        self.log("=" * 50)
        
        # 启动爬取线程
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="状态: 运行中...", foreground="green")
        
        # 启动爬取线程
        self.stop_requested = False
        self.crawler_thread = threading.Thread(target=self.run_crawler, daemon=True)
        self.crawler_thread.start()
    
    def run_crawler(self):
        """运行爬虫（在线程中）"""
        try:
            # 应用补丁：每页保存数据，支持停止标志
            weibo_patch.apply_patch()
            
            # 应用CSV补丁：修改文件名为_posts.csv和_comments.csv
            try:
                weibo_csv_patch.apply_patch()
            except Exception as e:
                self.log(f"应用CSV补丁失败: {str(e)}", "ERROR")
                # 继续运行，不使用CSV补丁
            
            # 重置停止标志
            weibo_patch.set_stop_flag(False)
            
            # 重定向日志输出
            import logging
            logger = logging.getLogger("weibo")
            
            # 创建自定义日志处理器
            class GUILogHandler(logging.Handler):
                def __init__(self, gui):
                    super().__init__()
                    self.gui = gui
                
                def emit(self, record):
                    if not self.gui.stop_requested:  # 如果已请求停止，不再显示新日志
                        msg = self.format(record)
                        level = record.levelname
                        self.gui.root.after(0, lambda m=msg, l=level: self.gui.log(m, l))
            
            handler = GUILogHandler(self)
            handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(handler)
            
            # 根据采集模式运行不同的爬虫
            mode = self.config.get("crawl_mode", "user")
            # 确保output_dir是绝对路径（用于keyword_search和hot_search）
            output_dir = os.path.join(get_base_dir(), "weibo")
            
            if mode == "single_link":
                # 单链接模式：使用单链接爬取模块
                import single_link
                single_link.crawl_single_weibo(self.config)
            elif mode == "keyword":
                # 关键词模式：使用关键词搜索模块
                import keyword_search
                keyword_config = self.config.copy()
                keyword_config["output_dir"] = output_dir
                keyword_search.search_by_keywords(keyword_config)
            elif mode == "topic":
                # 话题模式：使用关键词搜索模块（话题只是特殊格式的关键词）
                import keyword_search
                # 将话题格式化为 #话题名# 格式，并转换为关键词列表
                search_topics = self.config.get("search_topics", [])
                if isinstance(search_topics, str):
                    search_topics = [t.strip() for t in search_topics.split(",") if t.strip()]
                
                # 处理话题格式：确保为 #话题名# 格式
                formatted_topics = []
                for topic in search_topics:
                    topic = topic.strip()
                    # 移除已有的#号
                    topic = topic.strip("#")
                    # 确保格式为 #话题名#
                    formatted_topic = f"#{topic}#"
                    formatted_topics.append(formatted_topic)
                
                # 将话题作为关键词处理
                topic_config = self.config.copy()
                topic_config["search_keywords"] = formatted_topics
                topic_config["max_search_count"] = topic_config.get("max_topic_search_count", 100)
                topic_config["output_dir"] = output_dir
                keyword_search.search_by_keywords(topic_config)
            elif mode == "hot_search":
                # 热搜模式：使用热搜爬虫模块
                import hot_search
                hot_config = self.config.copy()
                hot_config["output_dir"] = output_dir
                hot_search.crawl_hot_search(hot_config)
            else:
                # 用户模式：使用原有的weibo.main()
                weibo.main()
            
            # 无论是否停止，都要调用crawl_finished更新UI
            # 检查停止标志状态
            was_stopped = weibo_patch.get_stop_flag() or self.stop_requested
            self.root.after(0, lambda: self.crawl_finished(was_stopped))
        except KeyboardInterrupt:
            # 被中断
            self.root.after(0, lambda: self.log("爬取被中断", "WARNING"))
            self.root.after(0, self.crawl_finished)
        except Exception as e:
            error_msg = str(e)
            self.crawler_exception = error_msg
            self.root.after(0, lambda: self.log(f"爬取过程中出错: {error_msg}", "ERROR"))
            self.root.after(0, self.crawl_finished)
        finally:
            # 重置停止标志
            weibo_patch.set_stop_flag(False)
    
    def crawl_finished(self, was_stopped=None):
        """爬取完成"""
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        # 检查文件是否已保存
        result_folder = "weibo"
        files = []
        if os.path.exists(result_folder):
            for root, dirs, filenames in os.walk(result_folder):
                for filename in filenames:
                    if filename.endswith(('.csv', '.json')):
                        files.append(os.path.join(root, filename))
        
        # 确定是否被停止
        if was_stopped is None:
            was_stopped = self.stop_requested or weibo_patch.get_stop_flag()
        
        # 检查是否有异常
        if self.crawler_exception:
            self.status_label.config(text="状态: 出错", foreground="red")
            self.log(f"爬取过程中出错: {self.crawler_exception}", "ERROR")
            if files:
                messagebox.showerror("错误", 
                    f"爬取过程中出错:\n{self.crawler_exception}\n\n但已保存 {len(files)} 个文件到 weibo 文件夹")
            else:
                messagebox.showerror("错误", 
                    f"爬取过程中出错:\n{self.crawler_exception}\n\n未找到保存的文件，请检查日志")
            self.crawler_exception = None
        elif was_stopped:
            self.status_label.config(text="状态: 已停止", foreground="red")
            self.log("爬取已停止")
            if files:
                self.log(f"已保存 {len(files)} 个文件")
                messagebox.showinfo("已停止", f"爬取已停止\n已保存 {len(files)} 个文件到 weibo 文件夹")
            else:
                self.log("警告: 未找到保存的文件", "WARNING")
                messagebox.showwarning("已停止", "爬取已停止\n但未找到保存的文件，可能没有爬取到数据")
            self.stop_requested = False
            weibo_patch.set_stop_flag(False)
        else:
            self.status_label.config(text="状态: 已完成", foreground="blue")
            self.log("爬取任务完成")
            if files:
                self.log(f"已保存 {len(files)} 个文件")
                messagebox.showinfo("完成", f"爬取任务已完成\n已保存 {len(files)} 个文件到 weibo 文件夹")
            else:
                self.log("警告: 未找到保存的文件", "WARNING")
                messagebox.showwarning("警告", 
                    "爬取完成，但未找到保存的文件\n可能原因：\n1. 没有爬取到数据\n2. 文件保存失败\n请检查日志查看详细信息")
    
    def stop_crawl(self):
        """停止爬取"""
        if not self.is_running:
            return
            
        if messagebox.askyesno("确认", "确定要停止爬取吗？\n程序将在当前页爬取完成后停止\n已爬取的数据会立即保存"):
            self.stop_requested = True
            # 设置停止标志，让爬虫在下一页开始时检查并停止
            weibo_patch.set_stop_flag(True)
            self.is_running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="状态: 正在停止...", foreground="orange")
            self.log("用户请求停止爬取，将在当前页完成后停止...")
            self.log("注意：当前页的数据会自动保存")
    
    def on_crawl_mode_changed(self, event=None):
        """采集模式切换时的回调"""
        mode = self.crawl_mode.get()
        is_user_mode = (mode == "用户模式")
        is_keyword_mode = (mode == "关键词模式")
        is_topic_mode = (mode == "话题模式")
        is_hot_search_mode = (mode == "热搜模式")
        is_single_link_mode = (mode == "单链接模式")
        
        # 用户模式：显示用户相关配置，隐藏关键词和话题模式配置
        # 关键词模式：隐藏用户相关配置，显示关键词模式配置，隐藏话题模式配置
        # 话题模式：隐藏用户相关配置，显示话题模式配置，隐藏关键词模式配置
        # 热搜模式：隐藏用户相关配置，显示热搜模式配置，隐藏关键词和话题模式配置
        
        # 显示/隐藏爬取类型（仅用户模式）
        if is_user_mode:
            self.crawl_type_frame.grid()
        else:
            self.crawl_type_frame.grid_remove()
        
        # 显示/隐藏关键词过滤（仅用户模式）
        if is_user_mode:
            self.keyword_filter_frame.grid()
        else:
            self.keyword_filter_frame.grid_remove()
        
        # 显示/隐藏关键词模式配置（仅关键词模式）
        if is_keyword_mode:
            self.keyword_mode_frame.grid()
        else:
            self.keyword_mode_frame.grid_remove()
        
        # 显示/隐藏话题模式配置（仅话题模式）
        if is_topic_mode:
            self.topic_mode_frame.grid()
        else:
            self.topic_mode_frame.grid_remove()
        
        # 显示/隐藏热搜模式配置（仅热搜模式）
        if is_hot_search_mode:
            self.hot_search_mode_frame.grid()
        else:
            self.hot_search_mode_frame.grid_remove()
        
        # 显示/隐藏单链接模式配置（仅单链接模式）
        if is_single_link_mode:
            self.single_link_mode_frame.grid()
        else:
            self.single_link_mode_frame.grid_remove()
        
        # 结束日期对所有模式都显示
        # （用户模式、关键词模式、话题模式、热搜模式、单链接模式都支持结束日期）
        
        # 更新用户面板的显示
        if hasattr(self, 'user_panel'):
            if is_user_mode:
                self.user_panel.grid()
            else:
                self.user_panel.grid_remove()
        
        # 触发热搜模式配置更新
        if is_hot_search_mode:
            self.on_hot_search_mode_changed()
    
    def check_comment_config(self):
        """检查评论/转发配置"""
        write_modes = self.config.get("write_mode", [])
        download_comment = self.config.get("download_comment", 0)
        download_repost = self.config.get("download_repost", 0)
        
        # 现在CSV模式也支持评论/转发，所以不需要检查SQLite
        if (download_comment == 1 or download_repost == 1) and "csv" in write_modes:
            self.log("提示：评论/转发将直接保存为CSV文件", "INFO")
    
    def refresh_hot_search_list(self):
        """刷新热搜榜列表"""
        cookie = self.cookie_text.get("1.0", tk.END).strip()
        if not cookie or cookie == "your cookie":
            messagebox.showwarning("警告", "请先设置Cookie才能获取热搜榜")
            return
        
        self.log("正在获取热搜榜，请稍候...")
        
        # 在新线程中获取热搜榜，避免阻塞UI
        def get_hot_search():
            try:
                from hot_search import WeiboHotSearchCrawler
                temp_config = self.config.copy()
                temp_config['cookie'] = cookie
                crawler = WeiboHotSearchCrawler(temp_config)
                hot_topics = crawler.get_hot_search_list()
                
                if hot_topics:
                    # 在UI线程中更新显示
                    self.root.after(0, lambda: self.on_hot_search_list_refreshed(hot_topics))
                else:
                    self.root.after(0, lambda: messagebox.showwarning("警告", "未能获取热搜榜，请检查网络连接和Cookie设置"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", f"获取热搜榜失败: {str(e)}"))
        
        threading.Thread(target=get_hot_search, daemon=True).start()
    
    def on_hot_search_list_refreshed(self, hot_topics):
        """热搜榜刷新完成后的回调"""
        self.log(f"成功获取 {len(hot_topics)} 个热搜话题")
        # 显示前10个
        for idx, topic_info in enumerate(hot_topics[:10]):
            self.log(f"  {topic_info['rank']}. {topic_info['keyword']}")
        if len(hot_topics) > 10:
            self.log(f"  ... 还有 {len(hot_topics) - 10} 个话题")
        
        # 创建选择对话框
        self.show_hot_search_selection_dialog(hot_topics)
    
    def show_hot_search_selection_dialog(self, hot_topics):
        """显示热搜话题选择对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("选择热搜话题")
        dialog.geometry("600x500")
        
        # 说明标签
        ttk.Label(dialog, text="请选择要采集的热搜话题（可多选）", font=("", 10)).pack(pady=10)
        
        # 创建列表框（支持多选）
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # 添加热搜话题
        for topic_info in hot_topics:
            listbox.insert(tk.END, f"{topic_info['rank']}. {topic_info['keyword']}")
        
        # 全选/取消全选按钮
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=5)
        ttk.Button(button_frame, text="全选", command=lambda: [listbox.select_set(0, tk.END)]).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消全选", command=lambda: listbox.selection_clear(0, tk.END)).pack(side=tk.LEFT, padx=5)
        
        selected_items = []
        
        def confirm():
            nonlocal selected_items
            selections = listbox.curselection()
            selected_items = [hot_topics[idx]['keyword'] for idx in selections]
            dialog.destroy()
            # 更新输入框
            if selected_items:
                self.selected_hot_topics.set(",".join(selected_items))
                self.use_all_hot_topics.set(False)
            else:
                self.use_all_hot_topics.set(True)
        
        def select_all():
            self.use_all_hot_topics.set(True)
            self.selected_hot_topics.set("")
            dialog.destroy()
        
        # 确认和取消按钮
        confirm_frame = ttk.Frame(dialog)
        confirm_frame.pack(pady=10)
        ttk.Button(confirm_frame, text="使用所有热搜", command=select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(confirm_frame, text="确认选择", command=confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(confirm_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def on_hot_search_mode_changed(self):
        """热搜模式配置变更时的回调"""
        use_all = self.use_all_hot_topics.get()
        # 如果选择使用所有热搜，禁用话题选择输入框
        # 如果选择特定话题，启用话题选择输入框
        if hasattr(self, 'selected_hot_topics'):
            # 注意：这里不能直接修改Entry的状态，因为selected_hot_topics是StringVar
            # 可以在界面显示上进行提示，或者创建一个Entry控件来显示
            pass
    
    def open_result_folder(self):
        """打开结果文件夹"""
        result_folder = "weibo"
        if os.path.exists(result_folder):
            if sys.platform == "win32":
                os.startfile(result_folder)
            elif sys.platform == "darwin":
                os.system(f"open {result_folder}")
            else:
                os.system(f"xdg-open {result_folder}")
        else:
            messagebox.showinfo("提示", "结果文件夹不存在，请先运行爬取任务")
    
    def on_closing(self):
        """窗口关闭时的处理"""
        try:
            # 自动保存所有配置（包括清空的搜索栏）
            self.save_all_config_silent()
            # 自动保存用户ID列表
            if hasattr(self, 'user_listbox'):
                self.save_user_id_list()
        except Exception as e:
            # 即使保存失败也允许关闭窗口
            self.log(f"关闭时保存配置失败: {str(e)}", "WARNING")
        finally:
            # 关闭窗口
            self.root.destroy()
    
    def save_all_config_silent(self):
        """静默保存所有配置（不显示消息框）"""
        try:
            # 更新配置字典
            self.config["only_crawl_original"] = 0 if self.crawl_type.get() == "全部" else 1
            
            # 处理起始日期
            since_date_str = self.since_date.get().strip()
            if not since_date_str:
                self.config["since_date"] = "1900-01-01"
            elif since_date_str.endswith("天前"):
                try:
                    days = int(since_date_str.replace("天前", "").strip())
                    self.config["since_date"] = days
                except:
                    self.config["since_date"] = since_date_str
            elif since_date_str.isdigit():
                try:
                    self.config["since_date"] = int(since_date_str)
                except:
                    self.config["since_date"] = since_date_str
            else:
                self.config["since_date"] = since_date_str
            
            # 处理结束日期
            end_date_str = self.end_date.get().strip()
            if not end_date_str:
                self.config["end_date"] = datetime.now().strftime("%Y-%m-%d")
            else:
                try:
                    datetime.strptime(end_date_str, "%Y-%m-%d")
                    self.config["end_date"] = end_date_str
                except ValueError:
                    self.config["end_date"] = datetime.now().strftime("%Y-%m-%d")
            
            self.config["start_page"] = int(self.start_page.get())
            self.config["page_weibo_count"] = int(self.page_weibo_count.get())
            
            # 保存格式
            write_modes = []
            if self.write_mode_csv.get():
                write_modes.append("csv")
            if self.write_mode_json.get():
                write_modes.append("json")
            self.config["write_mode"] = write_modes if write_modes else ["csv"]
            
            # 下载选项
            self.config["original_pic_download"] = 1 if self.original_pic.get() else 0
            self.config["retweet_pic_download"] = 1 if self.retweet_pic.get() else 0
            self.config["original_video_download"] = 1 if self.original_video.get() else 0
            self.config["retweet_video_download"] = 1 if self.retweet_video.get() else 0
            
            # 评论和转发
            self.config["download_comment"] = 1 if self.download_comment.get() else 0
            self.config["download_repost"] = 1 if self.download_repost.get() else 0
            self.config["comment_max_download_count"] = int(self.comment_max.get())
            self.config["repost_max_download_count"] = int(self.repost_max.get())
            
            # 采集模式
            mode = self.crawl_mode.get()
            if mode == "用户模式":
                self.config["crawl_mode"] = "user"
            elif mode == "关键词模式":
                self.config["crawl_mode"] = "keyword"
            elif mode == "话题模式":
                self.config["crawl_mode"] = "topic"
            elif mode == "热搜模式":
                self.config["crawl_mode"] = "hot_search"
            elif mode == "单链接模式":
                self.config["crawl_mode"] = "single_link"
            
            # 关键词过滤（用户模式下，在用户微博中搜索关键词）
            keywords_str = self.keywords.get().strip()
            if keywords_str:
                query_list = [kw.strip() for kw in keywords_str.split(",") if kw.strip()]
                self.config["query_list"] = query_list
            else:
                self.config["query_list"] = []
            
            # 关键词搜索（关键词模式）
            if mode == "关键词模式":
                search_keywords_str = self.search_keywords.get().strip()
                if search_keywords_str:
                    search_keywords_list = [kw.strip() for kw in search_keywords_str.split(",") if kw.strip()]
                    self.config["search_keywords"] = search_keywords_list
                else:
                    self.config["search_keywords"] = []
            
            # 话题搜索（话题模式）
            if mode == "话题模式":
                search_topics_str = self.search_topics.get().strip()
                if search_topics_str:
                    search_topics_list = [t.strip() for t in search_topics_str.split(",") if t.strip()]
                    self.config["search_topics"] = search_topics_list
                else:
                    self.config["search_topics"] = []
            
            # 最大搜索条数（关键词模式）
            if mode == "关键词模式":
                try:
                    self.config["max_search_count"] = int(self.max_search_count.get())
                except:
                    self.config["max_search_count"] = 100
            
            # 最大搜索条数（话题模式）
            if mode == "话题模式":
                try:
                    self.config["max_topic_search_count"] = int(self.max_topic_search_count.get())
                except:
                    self.config["max_topic_search_count"] = 100
            
            # 热搜模式配置
            if mode == "热搜模式":
                try:
                    self.config["max_hot_topics"] = int(self.max_hot_topics.get())
                except:
                    self.config["max_hot_topics"] = 50
                
                try:
                    self.config["posts_per_hot_topic"] = int(self.posts_per_hot_topic.get())
                except:
                    self.config["posts_per_hot_topic"] = 100
                
                self.config["use_all_hot_topics"] = self.use_all_hot_topics.get()
                
                selected_topics_str = self.selected_hot_topics.get().strip()
                if selected_topics_str:
                    selected_topics_list = [t.strip() for t in selected_topics_str.split(",") if t.strip()]
                    self.config["selected_hot_topics"] = selected_topics_list
                else:
                    self.config["selected_hot_topics"] = []
            
            # 单链接模式配置
            if mode == "单链接模式":
                weibo_url_str = self.weibo_url.get().strip()
                self.config["weibo_url"] = weibo_url_str
            
            # Cookie
            self.config["cookie"] = self.cookie_text.get("1.0", tk.END).strip()
            
            # 保存配置（静默，不显示消息框）
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            # 静默处理错误，不显示消息框
            pass


def main():
    """主函数"""
    root = tk.Tk()
    app = WeiboCrawlerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

