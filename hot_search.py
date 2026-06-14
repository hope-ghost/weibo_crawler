#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
热搜模块 - 自动获取热搜榜并采集相关微博
支持获取热搜榜前50话题，并依次进行采集
用户可以自定义每个热搜话题采集多少帖子，或单独采集某个或某几个热搜话题
"""

import os
import re
import sys
import json
import logging
import random
import time
from datetime import datetime, timedelta
from urllib.parse import unquote, quote
from collections import OrderedDict

import requests
from lxml import etree

# 复用keyword_search模块的搜索功能
from keyword_search import WeiboKeywordSearcher

logger = logging.getLogger("weibo")


class WeiboHotSearchCrawler:
    """微博热搜爬虫"""
    
    def __init__(self, config):
        self.config = config
        self.cookie = config.get("cookie", "")
        self.base_url = 'https://s.weibo.com'
        self.max_topics = config.get("max_hot_topics", 50)  # 默认获取前50个热搜
        self.default_posts_per_topic = config.get("posts_per_hot_topic", 100)  # 每个话题默认采集数量
        self.selected_topics = config.get("selected_hot_topics", [])  # 用户选择的话题列表
        self.use_all_topics = config.get("use_all_hot_topics", True)  # 是否使用所有热搜话题
        
        # 创建会话
        self.session = requests.Session()
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'cookie': self.cookie,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://s.weibo.com/'
        }
        self.session.headers.update(self.headers)
        
        # 停止标志
        self.stop_flag = False
        
        # 初始化会话
        try:
            self.session.get('https://s.weibo.com/', timeout=10)
            time.sleep(1)
        except:
            pass
    
    def set_stop_flag(self):
        """设置停止标志"""
        self.stop_flag = True
    
    def check_stop_flag(self):
        """检查停止标志"""
        try:
            import weibo_patch
            if weibo_patch.get_stop_flag():
                self.stop_flag = True
        except:
            pass
    
    def get_hot_search_list(self):
        """
        获取微博热搜榜前N个话题
        
        Returns:
            list: 热搜话题列表，每个元素为字典，包含 'keyword' 和 'rank' 字段
        """
        self.check_stop_flag()
        if self.stop_flag:
            return []
        
        hot_search_list = []
        
        try:
            # 尝试多种方式获取热搜榜
            # 方式1: 从热搜页面获取
            url = 'https://s.weibo.com/top/summary'
            logger.info("正在获取热搜榜...")
            
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    self.check_stop_flag()
                    if self.stop_flag:
                        return []
                    
                    response = self.session.get(url, timeout=15, allow_redirects=True)
                    
                    if response.status_code == 418 or response.status_code == 403:
                        logger.warning(f"请求被拒绝 ({response.status_code})，尝试其他方式获取热搜")
                        break
                    elif response.status_code != 200:
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(2)
                            continue
                        else:
                            logger.error(f"获取热搜榜失败，状态码: {response.status_code}")
                            break
                    
                    html = etree.HTML(response.text)
                    if html is None:
                        retry_count += 1
                        if retry_count < max_retries:
                            time.sleep(2)
                            continue
                        break
                    
                    # 解析热搜列表
                    # 热搜话题通常在 <td class="td-02"> 或 <a> 标签中
                    hot_items = html.xpath('//td[@class="td-02"]/a | //div[@class="trend"]//a | //li[@class="list_a"]//a')
                    
                    if not hot_items:
                        # 尝试另一种选择器
                        hot_items = html.xpath('//div[contains(@class, "trend")]//a | //a[contains(@href, "q=")]')
                    
                    if not hot_items:
                        # 尝试从JSON数据中解析
                        script_tags = html.xpath('//script[contains(text(), "hotSearchList") or contains(text(), "hotList")]')
                        for script in script_tags:
                            script_text = script.text
                            if script_text:
                                # 尝试提取JSON数据
                                json_match = re.search(r'\{.*?"list".*?\}', script_text, re.DOTALL)
                                if json_match:
                                    try:
                                        json_data = json.loads(json_match.group())
                                        if 'list' in json_data:
                                            for item in json_data['list']:
                                                keyword = item.get('word', '') or item.get('keyword', '') or item.get('title', '')
                                                if keyword:
                                                    hot_search_list.append({
                                                        'keyword': keyword.strip(),
                                                        'rank': len(hot_search_list) + 1
                                                    })
                                    except:
                                        pass
                    
                    # 从HTML元素中提取
                    for idx, item in enumerate(hot_items[:self.max_topics]):
                        self.check_stop_flag()
                        if self.stop_flag:
                            break
                        
                        # 获取文本内容
                        keyword = item.xpath('string(.)').strip()
                        if not keyword:
                            href = item.xpath('@href')
                            if href:
                                # 从URL中提取关键词
                                url_str = href[0]
                                if 'q=' in url_str:
                                    keyword = unquote(url_str.split('q=')[1].split('&')[0])
                        
                        if keyword and keyword not in [item['keyword'] for item in hot_search_list]:
                            hot_search_list.append({
                                'keyword': keyword,
                                'rank': len(hot_search_list) + 1
                            })
                    
                    if hot_search_list:
                        break
                    
                except Exception as e:
                    retry_count += 1
                    logger.warning(f"获取热搜榜出错 (尝试 {retry_count}/{max_retries}): {e}")
                    if retry_count < max_retries:
                        time.sleep(2)
                    else:
                        logger.error(f"获取热搜榜失败: {e}")
            
            # 如果仍然没有获取到，尝试API方式
            if not hot_search_list:
                logger.info("尝试通过API方式获取热搜榜...")
                try:
                    # 微博热搜API (可能不稳定)
                    api_url = 'https://weibo.com/ajax/side/hotSearch'
                    response = self.session.get(api_url, timeout=15)
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            if 'data' in data:
                                realtime_items = data['data'].get('realtime', [])
                                for idx, item in enumerate(realtime_items[:self.max_topics]):
                                    keyword = item.get('word', '') or item.get('note', '') or item.get('title', '')
                                    if keyword:
                                        hot_search_list.append({
                                            'keyword': keyword.strip(),
                                            'rank': len(hot_search_list) + 1
                                        })
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"通过API获取热搜失败: {e}")
            
            if hot_search_list:
                logger.info(f"成功获取 {len(hot_search_list)} 个热搜话题")
                for idx, item in enumerate(hot_search_list[:10]):  # 只显示前10个
                    logger.info(f"  {item['rank']}. {item['keyword']}")
                if len(hot_search_list) > 10:
                    logger.info(f"  ... 还有 {len(hot_search_list) - 10} 个话题")
            else:
                logger.warning("未能获取到热搜话题，请检查网络连接和Cookie设置")
            
        except Exception as e:
            logger.error(f"获取热搜榜时出错: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return hot_search_list
    
    def crawl_hot_search(self):
        """
        爬取热搜话题的微博
        
        根据配置选择使用所有热搜话题或用户选择的话题
        为每个话题采集指定数量的微博
        """
        logger.info("=" * 60)
        logger.info("开始热搜模式采集")
        logger.info("=" * 60)
        
        # 获取热搜列表
        all_topics = self.get_hot_search_list()
        
        if not all_topics:
            logger.error("未能获取热搜列表，请检查网络连接和Cookie设置")
            return
        
        # 确定要采集的话题列表
        if self.use_all_topics:
            # 使用所有热搜话题
            topics_to_crawl = all_topics
            logger.info(f"将采集所有 {len(topics_to_crawl)} 个热搜话题")
        else:
            # 只采集用户选择的话题
            if not self.selected_topics:
                logger.warning("已选择只采集指定话题，但未选择任何话题，使用所有热搜")
                topics_to_crawl = all_topics
            else:
                topics_to_crawl = []
                used_topic_keys = set()  # 记录已匹配的话题关键字，避免重复匹配
                
                # 为每个用户选择的话题进行匹配
                for selected in self.selected_topics:
                    selected = selected.strip()
                    selected_clean = selected.strip('#').strip().lower()
                    matched_topic = None
                    
                    # 精确匹配（去除#号后完全相等）
                    # 使用精确匹配避免部分匹配导致的错误（如"国考"匹配到"国考图推"）
                    for topic in all_topics:
                        topic_clean = topic['keyword'].strip().strip('#').strip().lower()
                        if selected_clean == topic_clean:
                            # 检查是否已使用
                            if topic_clean not in used_topic_keys:
                                matched_topic = topic
                                used_topic_keys.add(topic_clean)
                                logger.info(f"匹配热搜话题: '{selected}' -> '{topic['keyword']}'")
                                break
                            else:
                                # 话题已被使用，跳过
                                logger.warning(f"话题 '{topic['keyword']}' 已被匹配，跳过重复匹配")
                                break
                    
                    # 第三步：如果都没匹配到，使用用户输入的原始话题
                    if not matched_topic:
                        selected_key = selected_clean
                        if selected_key not in used_topic_keys:
                            matched_topic = {
                                'keyword': selected,
                                'rank': len(topics_to_crawl) + 1
                            }
                            used_topic_keys.add(selected_key)
                            logger.info(f"使用原始输入: '{selected}'")
                    
                    if matched_topic:
                        topics_to_crawl.append(matched_topic)
                
                logger.info(f"将采集用户选择的 {len(topics_to_crawl)} 个话题:")
                for topic_info in topics_to_crawl:
                    logger.info(f"  {topic_info.get('rank', '?')}. {topic_info['keyword']}")
        
        if not topics_to_crawl:
            logger.error("没有话题需要采集")
            return
        
        # 获取每个话题的采集数量配置
        topic_counts = self.config.get("hot_topic_counts", {})  # 格式: {"话题名": 数量}
        
        # 创建搜索器配置
        search_config = self.config.copy()
        
        # 热搜模式特殊处理：强制使用最近的时间范围，确保能获取到最新发布的帖子
        # 设置起始日期为7天前，结束日期为当前时间（包含今天）
        # 使用7天是为了避免触发快速定位（时间跨度超过7天会触发快速定位）
        # 快速定位会从历史数据开始查找，可能会影响获取最新帖子的效率
        from datetime import datetime, timedelta
        now = datetime.now()
        search_config['start_date'] = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        search_config['end_date'] = now.strftime('%Y-%m-%d')
        # 设置since_date为一个明确的日期（7天前），避免触发快速定位
        # 这样搜索会直接从7天前开始，按时间倒序获取最新发布的帖子
        search_config['since_date'] = search_config['start_date']
        
        logger.info(f"热搜模式时间范围: {search_config['start_date']} 到 {search_config['end_date']} (最近7天，优先获取最新发布的帖子)")
        
        # 为每个话题采集微博
        total_crawled = 0
        for idx, topic_info in enumerate(topics_to_crawl):
            self.check_stop_flag()
            if self.stop_flag:
                logger.info("检测到停止请求，停止采集")
                break
            
            topic = topic_info['keyword']
            rank = topic_info.get('rank', idx + 1)
            
            # 确定该话题的采集数量
            posts_count = topic_counts.get(topic, self.default_posts_per_topic)
            
            logger.info("")
            logger.info("-" * 60)
            logger.info(f"正在采集第 {rank} 个热搜话题: {topic}")
            logger.info(f"计划采集 {posts_count} 条微博")
            logger.info("-" * 60)
            
            try:
                # 格式化话题为 #话题名# 格式
                # 热搜榜中的话题应该以话题形式搜索，确保搜索到的是真正参与该话题的微博
                formatted_topic = topic.strip()
                # 移除已有的#号（如果有）
                if formatted_topic.startswith('#') and formatted_topic.endswith('#'):
                    # 已经是话题格式，移除#号后重新添加（确保格式统一）
                    formatted_topic = formatted_topic.strip('#')
                # 确保格式为 #话题名#
                formatted_topic = f"#{formatted_topic}#"
                
                logger.info(f"格式化话题: {topic} -> {formatted_topic}")
                
                # 更新搜索配置
                topic_config = search_config.copy()
                topic_config['search_keywords'] = [formatted_topic]
                topic_config['max_search_count'] = posts_count
                
                # 重置结果计数器（在搜索器内部）
                # 创建搜索器并执行搜索
                searcher = WeiboKeywordSearcher(topic_config)
                searcher.result_count = 0  # 重置计数器
                
                # 执行搜索
                weibos = searcher.search_keyword(formatted_topic)
                
                crawled_count = len(weibos) if weibos else 0
                total_crawled += crawled_count
                
                logger.info(f"话题 '{topic}' 采集完成，共获取 {crawled_count} 条微博")
                
                # 每个话题之间稍作延迟
                if idx < len(topics_to_crawl) - 1:
                    logger.info(f"等待 {random.uniform(2, 4):.1f} 秒后继续下一个话题...")
                    time.sleep(random.uniform(2, 4))
                    
            except Exception as e:
                logger.error(f"采集话题 '{topic}' 时出错: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                continue
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"热搜模式采集完成！共采集 {len(topics_to_crawl)} 个话题，总计 {total_crawled} 条微博")
        logger.info("=" * 60)


def crawl_hot_search(config):
    """
    根据配置爬取热搜话题的微博
    
    Args:
        config: 配置字典，包含：
            - cookie: Cookie字符串
            - max_hot_topics: 最大热搜话题数（默认50）
            - posts_per_hot_topic: 每个话题默认采集数量（默认100）
            - selected_hot_topics: 用户选择的话题列表（可选）
            - use_all_hot_topics: 是否使用所有热搜话题（默认True）
            - hot_topic_counts: 每个话题的采集数量配置（可选，格式: {"话题名": 数量}）
            - 其他配置项（与keyword_search相同）
    """
    crawler = WeiboHotSearchCrawler(config)
    crawler.crawl_hot_search()


def main():
    """主函数，用于测试"""
    import json
    
    if len(sys.argv) < 2:
        print("用法: python hot_search.py <config.json>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    crawl_hot_search(config)


if __name__ == "__main__":
    main()
