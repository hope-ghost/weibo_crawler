#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
单链接爬取模块
支持从微博链接直接爬取单条微博数据
"""

import os
import re
import logging
import json
import requests
from collections import OrderedDict
from lxml import etree

import weibo
from util import csvutil

logger = logging.getLogger("weibo")


def extract_weibo_id_from_url(url):
    """
    从微博链接中提取微博ID（bid）
    支持的链接格式：
    - https://weibo.com/user_id/bid
    - https://m.weibo.cn/status/bid
    - https://m.weibo.cn/detail/weibo_id
    - https://weibo.com/user_id/bid?xxx
    """
    if not url:
        return None
    
    # 清理URL，去除可能的空格和换行
    url = url.strip()
    
    # 提取bid（微博短链接ID）
    # 格式1: https://weibo.com/user_id/bid 或 https://weibo.com/user_id/bid?xxx
    match = re.search(r'weibo\.com/\d+/([A-Za-z0-9]+)', url)
    if match:
        return match.group(1)
    
    # 格式2: https://m.weibo.cn/status/bid
    match = re.search(r'm\.weibo\.cn/status/([A-Za-z0-9]+)', url)
    if match:
        return match.group(1)
    
    # 格式3: https://m.weibo.cn/detail/weibo_id (数字ID)
    match = re.search(r'm\.weibo\.cn/detail/(\d+)', url)
    if match:
        return match.group(1)
    
    # 如果URL本身就是bid格式（纯字母数字）
    if re.match(r'^[A-Za-z0-9]+$', url):
        return url
    
    logger.warning(f"无法从URL中提取微博ID: {url}")
    return None


def crawl_single_weibo(config):
    """
    爬取单条微博
    
    :param config: 配置字典，需要包含：
        - weibo_url: 微博链接
        - cookie: Cookie字符串（可选）
        - 其他weibo.py需要的配置项
    """
    weibo_url = config.get("weibo_url", "").strip()
    if not weibo_url:
        logger.error("未提供微博链接")
        return
    
    # 提取微博ID
    bid = extract_weibo_id_from_url(weibo_url)
    if not bid:
        logger.error(f"无法从链接中提取微博ID: {weibo_url}")
        return
    
    logger.info(f"开始爬取微博，链接: {weibo_url}")
    logger.info(f"提取的微博ID: {bid}")
    
    try:
        # 为单链接模式准备配置（需要提供user_id_list和since_date等必需字段）
        single_link_config = config.copy()
        # 如果config中没有user_id_list，设置一个空列表（Weibo类会处理）
        if "user_id_list" not in single_link_config:
            single_link_config["user_id_list"] = []
        # 确保有since_date（单链接模式不需要日期过滤，但Weibo类需要这个字段）
        if "since_date" not in single_link_config:
            single_link_config["since_date"] = "1900-01-01"  # 设置为很早的日期，表示爬取全部
        
        # 创建Weibo实例
        weibo_crawler = weibo.Weibo(single_link_config)
        
        # 尝试通过API获取微博详情
        # 方法1: 使用bid通过API获取
        weibo_data = None
        
        # 尝试使用weibo.com的API
        api_url = f"https://weibo.com/ajax/statuses/show?id={bid}&locale=zh-CN"
        headers = weibo_crawler.headers.copy()
        
        try:
            response = weibo_crawler.session.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("ok") == 1 and "data" in data:
                    weibo_info = data["data"]
                    # 转换为Weibo类期望的格式
                    weibo_data = {
                        "mblog": weibo_info
                    }
                    logger.info("通过API成功获取微博数据")
        except Exception as e:
            logger.debug(f"API方式获取失败: {e}")
        
        # 方法2: 如果API失败，尝试通过详情页获取
        if not weibo_data:
            try:
                # 如果是数字ID，直接使用get_long_weibo
                if bid.isdigit():
                    weibo_obj = weibo_crawler.get_long_weibo(bid)
                    if weibo_obj:
                        weibo_data = {"parsed": weibo_obj}
                        logger.info("通过详情页成功获取微博数据")
            except Exception as e:
                logger.debug(f"详情页方式获取失败: {e}")
        
        # 方法3: 如果还是失败，尝试使用m.weibo.cn的API
        if not weibo_data:
            try:
                detail_url = f"https://m.weibo.cn/detail/{bid}"
                response = weibo_crawler.session.get(detail_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    html = response.text
                    # 从HTML中提取status数据
                    if '"status":' in html:
                        html = html[html.find('"status":'):]
                        html = html[:html.rfind('"call"')]
                        html = html[:html.rfind(",")]
                        html = "{" + html + "}"
                        js = json.loads(html, strict=False)
                        weibo_info = js.get("status")
                        if weibo_info:
                            weibo_data = {"mblog": weibo_info}
                            logger.info("通过m.weibo.cn详情页成功获取微博数据")
            except Exception as e:
                logger.debug(f"m.weibo.cn方式获取失败: {e}")
        
        if not weibo_data:
            logger.error("无法获取微博数据，请检查链接是否正确或Cookie是否有效")
            return
        
        # 解析微博数据
        if "parsed" in weibo_data:
            weibo_obj = weibo_data["parsed"]
        else:
            # 使用get_one_weibo方法解析
            weibo_obj = weibo_crawler.get_one_weibo(weibo_data)
        
        if not weibo_obj:
            logger.error("解析微博数据失败")
            return
        
        # 标准化微博信息
        weibo_obj = weibo_crawler.standardize_info(weibo_obj)
        
        # 获取用户ID（用于创建user_config）
        user_id = weibo_obj.get("user_id", "unknown")
        if user_id == "unknown" or not user_id:
            # 如果无法获取user_id，使用一个默认值
            user_id = "single_link_user"
            logger.warning("无法获取用户ID，使用默认值")
        
        # 初始化user_config（必须在保存数据之前设置）
        from datetime import datetime
        user_config = {
            "user_id": str(user_id),
            "since_date": config.get("since_date", "1900-01-01"),
            "end_date": config.get("end_date", datetime.now().strftime("%Y-%m-%d")),
            "query_list": config.get("query_list", [])
        }
        weibo_crawler.initialize_info(user_config)
        
        # 设置用户信息（用于保存路径）
        weibo_crawler.user = {
            "id": str(user_id),
            "screen_name": weibo_obj.get("screen_name", "unknown"),
            "statuses_count": 1  # 单条微博，设置为1
        }
        
        # 保存微博数据
        weibo_list = [weibo_obj]
        weibo_crawler.weibo = weibo_list
        weibo_crawler.got_count = 1
        weibo_crawler.weibo_id_list = [weibo_obj["id"]]
        
        # 下载评论和转发（如果配置了）
        if config.get("download_comment", 0) == 1:
            max_comment_count = config.get("comment_max_download_count", 100)
            if "sqlite" in config.get("write_mode", []):
                # SQLite模式：使用sqlite_insert_comments
                weibo_crawler.get_weibo_comments(weibo_obj, max_comment_count, weibo_crawler.sqlite_insert_comments)
            else:
                # CSV模式：直接保存评论到CSV文件
                import csv as csv_module
                
                # 获取保存路径
                csv_path = weibo_crawler.get_filepath("csv")
                user_dir = os.path.dirname(csv_path)
                screen_name = weibo_crawler.user.get("screen_name", "unknown")
                safe_screen_name = re.sub(r'[\\/:*?"<>|]', "_", str(screen_name))
                weibo_id = str(weibo_obj.get("id", ""))
                
                # 评论CSV文件路径：<用户昵称>_<weibo_id>_comments.csv
                comments_csv_path = os.path.join(user_dir, f"{safe_screen_name}_{weibo_id}_comments.csv")
                
                # 创建状态变量（使用列表以便在闭包中修改）
                file_exists = [os.path.exists(comments_csv_path)]  # 使用列表存储状态
                comment_counter = [0]  # 使用列表以便在闭包中修改
                
                def comment_callback(weibo, comments):
                    """保存评论到CSV文件的回调函数"""
                    if not comments:
                        return
                    
                    with open(comments_csv_path, 'a', encoding='utf-8-sig', newline='') as f:
                        writer = csv_module.writer(f)
                        
                        # 如果是新文件，写入表头
                        if not file_exists[0]:
                            header = ['id', 'weibo_id', 'created_at', 'user_id', 'user_screen_name', 'text', 'pic_url', 'like_count']
                            writer.writerow(header)
                            file_exists[0] = True
                        
                        # 写入评论
                        for comment in comments:
                            if comment_counter[0] >= max_comment_count:
                                break
                            
                            comment_id = comment.get('id', '')
                            user = comment.get('user', {})
                            user_id = user.get('id', '') if isinstance(user, dict) else ''
                            screen_name = user.get('screen_name', '') if isinstance(user, dict) else ''
                            text = comment.get('text', '')
                            # 移除HTML标签
                            if text:
                                text = re.sub('<[^<]+?>', '', text).replace('\n', ' ').strip()
                            created_at = comment.get('created_at', '')
                            like_count = comment.get('like_count', 0)
                            pic_url = ''
                            if comment.get('pic'):
                                if isinstance(comment['pic'], dict):
                                    pic_url = comment['pic'].get('large', {}).get('url', '') or comment['pic'].get('url', '')
                            
                            writer.writerow([
                                '\t' + str(comment_id) if comment_id else '',
                                '\t' + str(weibo_id) if weibo_id else '',
                                created_at,
                                '\t' + str(user_id) if user_id else '',
                                screen_name,
                                text,
                                pic_url,
                                like_count
                            ])
                            comment_counter[0] += 1
                    
                    if len(comments) > 0:
                        logger.info(f"已保存 {len(comments)} 条评论到 {comments_csv_path} (累计: {comment_counter[0]}/{max_comment_count})")
                
                weibo_crawler.get_weibo_comments(weibo_obj, max_comment_count, comment_callback)
        
        if config.get("download_repost", 0) == 1:
            max_repost_count = config.get("repost_max_download_count", 100)
            if "sqlite" in config.get("write_mode", []):
                weibo_crawler.get_weibo_reposts(weibo_obj, max_repost_count, weibo_crawler.sqlite_insert_reposts)
            else:
                # CSV模式通过weibo_csv_patch自动处理
                def repost_callback(weibo, reposts):
                    logger.info(f"获取到 {len(reposts)} 条转发")
                weibo_crawler.get_weibo_reposts(weibo_obj, max_repost_count, repost_callback)
        
        # 保存到文件（wrote_count=0表示从0开始写入）
        weibo_crawler.write_data(0)
        
        logger.info("单条微博爬取完成")
        
    except Exception as e:
        logger.exception(f"爬取单条微博时出错: {e}")
        raise

