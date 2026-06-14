#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
关键词搜索模块 - 基于网页搜索
支持不依赖用户ID的全局关键词搜索，使用s.weibo.com网页搜索API
支持时间范围搜索和自动细分时间范围以获取更多数据
"""

import os
import re
import sys
import json
import logging
import random
from datetime import datetime, timedelta
from urllib.parse import unquote, quote
from collections import OrderedDict
import time

import requests
from lxml import etree

logger = logging.getLogger("weibo")


def standardize_date(created_at):
    """标准化微博发布时间"""
    if "刚刚" in created_at:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    elif "秒" in created_at:
        second = created_at[:created_at.find("秒")]
        second = timedelta(seconds=int(second))
        created_at = (datetime.now() - second).strftime("%Y-%m-%d %H:%M")
    elif "分钟" in created_at:
        minute = created_at[:created_at.find("分钟")]
        minute = timedelta(minutes=int(minute))
        created_at = (datetime.now() - minute).strftime("%Y-%m-%d %H:%M")
    elif "小时" in created_at:
        hour = created_at[:created_at.find("小时")]
        hour = timedelta(hours=int(hour))
        created_at = (datetime.now() - hour).strftime("%Y-%m-%d %H:%M")
    elif "今天" in created_at:
        today = datetime.now().strftime('%Y-%m-%d')
        created_at = today + ' ' + created_at[2:]
    elif '年' not in created_at:
        year = datetime.now().strftime("%Y")
        month = created_at[:2]
        day = created_at[3:5]
        time_str = created_at[6:]
        created_at = year + '-' + month + '-' + day + ' ' + time_str
    else:
        year = created_at[:4]
        month = created_at[5:7]
        day = created_at[8:10]
        time_str = created_at[11:]
        created_at = year + '-' + month + '-' + day + ' ' + time_str
    return created_at


def convert_weibo_type(weibo_type):
    """将微博类型转换成字符串"""
    if weibo_type == 0:
        return '&typeall=1'
    elif weibo_type == 1:
        return '&scope=ori'
    elif weibo_type == 2:
        return '&xsort=hot'
    elif weibo_type == 3:
        return '&atten=1'
    elif weibo_type == 4:
        return '&vip=1'
    elif weibo_type == 5:
        return '&category=4'
    elif weibo_type == 6:
        return '&viewpoint=1'
    return '&scope=ori'


def convert_contain_type(contain_type):
    """将包含类型转换成字符串"""
    if contain_type == 0:
        return '&suball=1'
    elif contain_type == 1:
        return '&haspic=1'
    elif contain_type == 2:
        return '&hasvideo=1'
    elif contain_type == 3:
        return '&hasmusic=1'
    elif contain_type == 4:
        return '&haslink=1'
    return '&suball=1'


class WeiboKeywordSearcher:
    """基于网页搜索的关键词搜索器"""
    
    def __init__(self, config):
        self.config = config
        self.cookie = config.get("cookie", "")
        self.base_url = 'https://s.weibo.com'
        self.further_threshold = config.get("further_threshold", 46)  # 细分阈值
        self.max_search_count = config.get("max_search_count", 100)
        self.result_count = 0
        self.stop_flag = False
        
        # 微博类型筛选
        self.weibo_type = convert_weibo_type(config.get("weibo_type", 1))  # 默认只搜索原创
        self.contain_type = convert_contain_type(config.get("contain_type", 0))
        
        # 时间范围：从since_date转换为start_date和end_date
        since_date = config.get("since_date", "")
        start_date = config.get("start_date", "")
        end_date = config.get("end_date", "")
        
        # 保存原始since_date，用于快速定位判断
        self.original_since_date = since_date if since_date else ""
        self.need_fast_locate = False  # 初始化快速定位标志
        
        # 优先使用start_date和end_date，如果没有则从since_date转换
        if start_date:
            try:
                self.start_date = datetime.strptime(start_date, '%Y-%m-%d')
            except:
                self.start_date = datetime.now() - timedelta(days=30)
        elif since_date:
            # 从since_date转换
            if since_date == "1900-01-01" or since_date == "" or str(since_date).strip() == "":
                # 爬取全部，设置一个很早的日期（用于快速定位）
                self.start_date = datetime(2010, 1, 1)
                self.need_fast_locate = True
            elif isinstance(since_date, int):
                # 天数
                self.start_date = datetime.now() - timedelta(days=since_date)
            elif isinstance(since_date, str):
                try:
                    # 尝试解析日期字符串
                    if 'T' in since_date:
                        self.start_date = datetime.strptime(since_date.split('T')[0], '%Y-%m-%d')
                    else:
                        self.start_date = datetime.strptime(since_date, '%Y-%m-%d')
                except:
                    self.start_date = datetime.now() - timedelta(days=30)
            else:
                self.start_date = datetime.now() - timedelta(days=30)
        else:
            # since_date为空，需要快速定位
            self.start_date = datetime(2010, 1, 1)
            self.need_fast_locate = True
        
        if end_date:
            try:
                self.end_date = datetime.strptime(end_date, '%Y-%m-%d')
            except:
                self.end_date = datetime.now()
        else:
            self.end_date = datetime.now()
        
        # 保存配置
        write_mode = config.get("write_mode", ["csv"])
        if isinstance(write_mode, str):
            self.write_mode = [write_mode]
        else:
            self.write_mode = write_mode
        # 确保output_dir是绝对路径
        output_dir = config.get("output_dir", "weibo")
        if not os.path.isabs(output_dir):
            # 如果是相对路径，需要导入pathutil来获取绝对路径
            try:
                from util.pathutil import get_base_dir, ensure_dir
                output_dir = os.path.join(get_base_dir(), output_dir)
                output_dir = ensure_dir(output_dir)
            except ImportError:
                # 如果无法导入，使用当前工作目录
                output_dir = os.path.abspath(output_dir)
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
        self.output_dir = output_dir
        
        # 下载配置
        self.original_pic_download = config.get("original_pic_download", 0)
        self.retweet_pic_download = config.get("retweet_pic_download", 0)
        self.original_video_download = config.get("original_video_download", 0)
        self.retweet_video_download = config.get("retweet_video_download", 0)
        self.download_comment = config.get("download_comment", 0)
        self.comment_max_download_count = config.get("comment_max_download_count", 100)
        self.download_repost = config.get("download_repost", 0)
        self.repost_max_download_count = config.get("repost_max_download_count", 100)
        
        # 创建会话
        self.session = requests.Session()
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'cookie': self.cookie,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://s.weibo.com/'
        }
        self.session.headers.update(self.headers)
        
        # 话题模式过滤标志：如果关键词格式为 #话题名#，需要过滤只保留包含目标话题的微博
        self.enable_topic_filter = config.get("enable_topic_filter", True)  # 默认启用话题过滤
        
        # 初始化会话：先访问首页
        try:
            self.session.get('https://s.weibo.com/', timeout=10)
            time.sleep(1)  # 延迟1秒
        except:
            pass
    
    def set_stop_flag(self):
        """设置停止标志"""
        self.stop_flag = True
    
    def check_stop_flag(self):
        """检查停止标志（从weibo_patch）"""
        try:
            import weibo_patch
            if weibo_patch.get_stop_flag():
                self.stop_flag = True
        except:
            pass
    
    def _sleep_with_stop_check(self, seconds):
        """分片sleep，期间检查停止标志
        
        将长的sleep拆分成多个1秒的sleep，在每个sleep之间检查停止标志。
        如果检测到停止请求，立即返回。
        """
        remaining = seconds
        while remaining > 0:
            self.check_stop_flag()
            if self.stop_flag:
                logger.info("检测到停止请求，中断等待")
                return
            sleep_time = min(1.0, remaining)  # 每次最多sleep 1秒
            time.sleep(sleep_time)
            remaining -= sleep_time
    
    def get_ip(self, bid):
        """获取微博发布IP地址"""
        url = f"https://weibo.com/ajax/statuses/show?id={bid}&locale=zh-CN"
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                ip_str = data.get("region_name", "")
                if ip_str:
                    ip_str = ip_str.split()[-1]
                return ip_str
        except:
            pass
        return ""
    
    def get_article_url(self, selector):
        """获取微博头条文章url"""
        article_url = ''
        text = selector.xpath('string(.)').replace('\u200b', '').replace('\ue627', '').replace('\n', '').replace(' ', '')
        if text.startswith('发布了头条文章'):
            urls = selector.xpath('.//a')
            for url in urls:
                if url.xpath('i[@class="wbicon"]/text()'):
                    if url.xpath('i[@class="wbicon"]/text()')[0] == 'O':
                        href = url.xpath('@href')
                        if href and href[0].startswith('http://t.cn'):
                            article_url = href[0]
                            break
        return article_url
    
    def get_location(self, selector):
        """获取微博发布位置"""
        a_list = selector.xpath('.//a')
        location = ''
        for a in a_list:
            if a.xpath('./i[@class="wbicon"]') and a.xpath('./i[@class="wbicon"]/text()'):
                if a.xpath('./i[@class="wbicon"]/text()')[0] == '2':
                    location = a.xpath('string(.)')[1:]
                    break
        return location
    
    def get_at_users(self, selector):
        """获取微博中@的用户昵称"""
        a_list = selector.xpath('.//a')
        at_users = ''
        at_list = []
        for a in a_list:
            href = a.xpath('@href')
            if href and len(unquote(href[0])) > 14:
                text = a.xpath('string(.)')
                if len(text) > 1:
                    if unquote(href[0])[14:] == text[1:]:
                        at_user = text[1:]
                        if at_user not in at_list:
                            at_list.append(at_user)
        if at_list:
            at_users = ','.join(at_list)
        return at_users
    
    def get_topics(self, selector):
        """获取参与的微博话题"""
        a_list = selector.xpath('.//a')
        topics = ''
        topic_list = []
        for a in a_list:
            text = a.xpath('string(.)')
            if len(text) > 2 and text[0] == '#' and text[-1] == '#':
                topic = text[1:-1]
                if topic not in topic_list:
                    topic_list.append(topic)
        if topic_list:
            topics = ','.join(topic_list)
        return topics
    
    def check_weibo_contains_topic(self, weibo, target_topic):
        """检查微博是否包含目标话题
        
        Args:
            weibo: 微博字典对象
            target_topic: 目标话题（格式：'#话题名#' 或 '话题名'）
            
        Returns:
            bool: 如果微博包含目标话题返回True，否则返回False
        """
        # 标准化目标话题格式（去除#号）
        if len(target_topic) > 2 and target_topic[0] == '#' and target_topic[-1] == '#':
            target_topic_name = target_topic[1:-1].strip()
        else:
            target_topic_name = target_topic.strip()
        
        if not target_topic_name:
            return False
        
        # 方法1：检查微博正文中是否包含完整的话题格式 #话题名#
        weibo_text = weibo.get('text', '')
        if weibo_text:
            # 检查完整的话题格式
            if f'#{target_topic_name}#' in weibo_text:
                return True
        
        # 方法2：检查微博中的话题字段（topics字段）
        topics_str = weibo.get('topics', '')
        if topics_str:
            topic_list = [t.strip() for t in topics_str.split(',') if t.strip()]
            # 精确匹配话题名称（不区分大小写）
            for topic in topic_list:
                if topic.lower() == target_topic_name.lower():
                    return True
        
        # 方法3：检查正文中是否有话题标签，即使格式略有不同
        # 使用正则表达式查找 #话题名# 格式
        if weibo_text:
            # 查找所有话题格式
            topic_pattern = r'#([^#]+)#'
            found_topics = re.findall(topic_pattern, weibo_text)
            for found_topic in found_topics:
                if found_topic.strip().lower() == target_topic_name.lower():
                    return True
        
        return False
    
    def get_vip(self, selector):
        """获取用户的VIP类型和等级信息"""
        vip_type = "非会员"
        vip_level = 0
        
        vip_container = selector.xpath('.//div[@class="user_vip_icon_container"]')
        if vip_container:
            svvip_img = vip_container[0].xpath('.//img[contains(@src, "svvip_")]')
            if svvip_img:
                vip_type = "超级会员"
                src = svvip_img[0].xpath('@src')
                if src:
                    level_match = re.search(r'svvip_(\d+)\.png', src[0])
                    if level_match:
                        vip_level = int(level_match.group(1))
            else:
                vip_img = vip_container[0].xpath('.//img[contains(@src, "vip_")]')
                if vip_img:
                    vip_type = "会员"
                    src = vip_img[0].xpath('@src')
                    if src:
                        level_match = re.search(r'vip_(\d+)\.png', src[0])
                        if level_match:
                            vip_level = int(level_match.group(1))
        
        return vip_type, vip_level
    
    def parse_weibo_item(self, sel, keyword):
        """解析单个微博项"""
        if self.stop_flag:
            return None
        
        info = sel.xpath("div[@class='card']/div[@class='card-feed']/div[@class='content']/div[@class='info']")
        if not info:
            return None
        
        try:
            weibo = OrderedDict()
            weibo['keyword'] = keyword
            
            # 获取微博ID和bid
            mid = sel.xpath('@mid')
            if mid:
                weibo['id'] = mid[0]
            else:
                return None
            
            bid_elem = sel.xpath('.//div[@class="from"]/a[1]/@href')
            if bid_elem:
                bid = bid_elem[0].split('/')[-1].split('?')[0]
                weibo['bid'] = bid
            else:
                return None
            
            # 用户信息
            user_href = info[0].xpath('div[2]/a/@href')
            if user_href:
                weibo['user_id'] = user_href[0].split('?')[0].split('/')[-1]
            
            screen_name_elem = info[0].xpath('div[2]/a/@nick-name')
            if screen_name_elem:
                weibo['screen_name'] = screen_name_elem[0]
            
            # VIP信息
            weibo['vip_type'], weibo['vip_level'] = self.get_vip(info[0])
            
            # 微博内容
            txt_sel = sel.xpath('.//p[@class="txt"]')
            retweet_sel = sel.xpath('.//div[@class="card-comment"]')
            retweet_txt_sel = None
            
            if txt_sel:
                txt_sel = txt_sel[0]
            
            if retweet_sel and retweet_sel[0].xpath('.//p[@class="txt"]'):
                retweet_txt_sel = retweet_sel[0].xpath('.//p[@class="txt"]')[0]
            
            content_full = sel.xpath('.//p[@node-type="feed_list_content_full"]')
            
            is_long_weibo = False
            is_long_retweet = False
            if content_full:
                if not retweet_sel:
                    txt_sel = content_full[0]
                    is_long_weibo = True
                elif len(content_full) == 2:
                    txt_sel = content_full[0]
                    retweet_txt_sel = content_full[1]
                    is_long_weibo = True
                    is_long_retweet = True
                elif retweet_sel[0].xpath('.//p[@node-type="feed_list_content_full"]'):
                    retweet_txt_sel = retweet_sel[0].xpath('.//p[@node-type="feed_list_content_full"]')[0]
                    is_long_retweet = True
                else:
                    txt_sel = content_full[0]
                    is_long_weibo = True
            
            if txt_sel:
                weibo['text'] = txt_sel.xpath('string(.)').replace('\u200b', '').replace('\ue627', '')
                weibo['article_url'] = self.get_article_url(txt_sel)
                weibo['location'] = self.get_location(txt_sel)
                if weibo['location']:
                    weibo['text'] = weibo['text'].replace('2' + weibo['location'], '')
                weibo['text'] = weibo['text'][2:].replace(' ', '')
                if is_long_weibo:
                    weibo['text'] = weibo['text'][:-4]
                weibo['at_users'] = self.get_at_users(txt_sel)
                weibo['topics'] = self.get_topics(txt_sel)
            
            # 转发、评论、点赞数
            reposts_elem = sel.xpath('.//a[@action-type="feed_list_forward"]/text()')
            reposts_count = "".join(reposts_elem) if reposts_elem else ""
            reposts_count = re.findall(r'\d+.*', reposts_count)
            weibo['reposts_count'] = reposts_count[0] if reposts_count else '0'
            
            comments_elem = sel.xpath('.//a[@action-type="feed_list_comment"]/text()')
            comments_count = comments_elem[0] if comments_elem else ""
            comments_count = re.findall(r'\d+.*', comments_count)
            weibo['comments_count'] = comments_count[0] if comments_count else '0'
            
            attitudes_elem = sel.xpath('.//a[@action-type="feed_list_like"]/button/span[2]/text()')
            attitudes_count = attitudes_elem[0] if attitudes_elem else ""
            attitudes_count = re.findall(r'\d+.*', attitudes_count)
            weibo['attitudes_count'] = attitudes_count[0] if attitudes_count else '0'
            
            # 发布时间
            created_at_elem = sel.xpath('.//div[@class="from"]/a[1]/text()')
            if created_at_elem:
                created_at = created_at_elem[0].replace(' ', '').replace('\n', '').split('前')[0]
                weibo['created_at'] = standardize_date(created_at)
            
            # 发布工具
            source_elem = sel.xpath('.//div[@class="from"]/a[2]/text()')
            weibo['source'] = source_elem[0] if source_elem else ''
            
            # 图片和视频
            pics = []
            is_exist_pic = sel.xpath('.//div[@class="media media-piclist"]')
            if is_exist_pic:
                pic_elems = is_exist_pic[0].xpath('ul[1]/li/img/@src')
                if pic_elems:
                    pics = [pic[8:] for pic in pic_elems]
                    pics = [re.sub(r'/.*?/', '/large/', pic, 1) for pic in pics]
                    pics = ['https://' + pic for pic in pics]
            
            video_url = ''
            is_exist_video = sel.xpath('.//div[@class="thumbnail"]//video-player')
            if is_exist_video:
                # 将 Element 对象转换为字符串
                video_element_str = etree.tostring(is_exist_video[0], encoding='unicode')
                video_match = re.findall(r'src:\'(.*?)\'', video_element_str)
                if video_match:
                    video_url = video_match[0].replace('&amp;', '&')
                    video_url = 'http:' + video_url
            
            if not retweet_sel:
                weibo['pics'] = ','.join(pics)
                weibo['video_url'] = video_url
            else:
                weibo['pics'] = ''
                weibo['video_url'] = ''
            
            weibo['retweet_id'] = ''
            
            # 处理转发微博
            if retweet_sel and retweet_sel[0].xpath('.//div[@node-type="feed_list_forwardContent"]/a[1]'):
                retweet_id_elem = retweet_sel[0].xpath('.//a[@action-type="feed_list_like"]/@action-data')
                if retweet_id_elem:
                    weibo['retweet_id'] = retweet_id_elem[0][4:]
            
            # IP地址
            weibo['ip'] = self.get_ip(bid)
            
            # 生成帖子链接
            if weibo.get('user_id') and weibo.get('bid'):
                weibo['weibo_url'] = f"https://weibo.com/{weibo['user_id']}/{weibo['bid']}"
            elif weibo.get('bid'):
                weibo['weibo_url'] = f"https://m.weibo.cn/status/{weibo['bid']}"
            else:
                weibo['weibo_url'] = ''
            
            # 用户认证类型
            avator = sel.xpath("div[@class='card']/div[@class='card-feed']/div[@class='avator']")
            if avator:
                user_auth = avator[0].xpath('.//svg/@id')
                if user_auth:
                    if user_auth[0] == 'woo_svg_vblue':
                        weibo['user_authentication'] = '蓝V'
                    elif user_auth[0] == 'woo_svg_vyellow':
                        weibo['user_authentication'] = '黄V'
                    elif user_auth[0] == 'woo_svg_vorange':
                        weibo['user_authentication'] = '红V'
                    elif user_auth[0] == 'woo_svg_vgold':
                        weibo['user_authentication'] = '金V'
                    else:
                        weibo['user_authentication'] = '普通用户'
                else:
                    weibo['user_authentication'] = '普通用户'
            else:
                weibo['user_authentication'] = '普通用户'
            
            return weibo
            
        except Exception as e:
            logger.error(f"解析微博时出错: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def parse_page(self, response_text, keyword):
        """解析搜索结果页面"""
        self.check_stop_flag()
        if self.stop_flag:
            return []
        
        weibo_list = []
        try:
            html = etree.HTML(response_text)
            weibo_cards = html.xpath("//div[@class='card-wrap']")
            
            # 判断是否为话题模式（关键词格式为 #话题名#）
            is_topic_mode = (len(keyword) > 2 and keyword[0] == '#' and keyword[-1] == '#')
            
            filtered_count = 0  # 统计被过滤掉的微博数量
            
            for sel in weibo_cards:
                self.check_stop_flag()
                if self.stop_flag:
                    break
                
                weibo = self.parse_weibo_item(sel, keyword)
                if weibo:
                    # 如果是话题模式且启用了过滤，检查微博是否包含目标话题
                    if is_topic_mode and self.enable_topic_filter:
                        if not self.check_weibo_contains_topic(weibo, keyword):
                            filtered_count += 1
                            continue  # 跳过不包含目标话题的微博
                    
                    weibo_list.append(weibo)
                    self.result_count += 1
                    
                    # 检查是否达到限制
                    if self.max_search_count > 0 and self.result_count >= self.max_search_count:
                        logger.info(f"已达到最大搜索条数限制: {self.max_search_count}")
                        self.stop_flag = True
                        break
            
            # 如果有过滤，记录日志
            if is_topic_mode and self.enable_topic_filter and filtered_count > 0:
                logger.info(f"话题模式过滤：已过滤 {filtered_count} 条不包含目标话题 '{keyword}' 的微博")
            
            # 每解析完一页，立即保存并下载资源
            if weibo_list:
                # 保存数据
                self.save_weibos(weibo_list, keyword)
                
                # 下载图片和视频
                if hasattr(self, 'download_media'):
                    try:
                        self.download_media(weibo_list, keyword)
                    except Exception as e:
                        logger.warning(f"下载图片/视频时出错: {e}")
                
                # 下载评论
                if self.download_comment and hasattr(self, 'download_comments'):
                    try:
                        self.download_comments(weibo_list, keyword)
                    except Exception as e:
                        logger.warning(f"下载评论时出错: {e}")
                    
        except Exception as e:
            logger.error(f"解析页面时出错: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return weibo_list
    
    def search_by_time_range(self, keyword, start_str, end_str, base_url, depth=0):
        """按时间范围搜索
        
        Args:
            keyword: 搜索关键词
            start_str: 开始时间字符串 (格式: YYYY-MM-DD-HH)
            end_str: 结束时间字符串 (格式: YYYY-MM-DD-HH)
            base_url: 基础URL
            depth: 递归深度，防止无限递归（0=天级别，1=小时级别）
        """
        self.check_stop_flag()
        if self.stop_flag:
            return []
        
        # 防止无限递归：如果已经是小时级别细分，不再继续细分
        if depth > 1:
            logger.warning(f"已达到最大细分深度，直接处理时间范围: {start_str} 到 {end_str}")
            # 直接处理，不再细分
            return self._process_time_range_directly(keyword, start_str, end_str, base_url)
        
        all_weibos = []
        url = base_url + self.weibo_type
        url += self.contain_type
        url += '&timescope=custom:{}:{}'.format(start_str, end_str)
        
        max_retries = 3
        retry_count = 0
        response = None
        html = None
        
        while retry_count < max_retries:
            # 检查停止标志
            self.check_stop_flag()
            if self.stop_flag:
                logger.info("检测到停止请求，停止搜索")
                return []
            
            try:
                logger.info(f"搜索关键词 '{keyword}' 时间范围: {start_str} 到 {end_str} (尝试 {retry_count + 1}/{max_retries})")
                
                # 添加随机延迟，避免请求过快（分片sleep以便检查停止标志）
                self._sleep_with_stop_check(random.uniform(1, 3))
                if self.stop_flag:
                    return []
                
                response = self.session.get(url, timeout=15, allow_redirects=True)
                
                # 检查状态码
                if response.status_code == 418:
                    logger.warning(f"请求被拒绝 (418)，可能是反爬虫机制，跳过该时间范围")
                    return []  # 跳过该时间范围，继续下一个
                elif response.status_code == 403:
                    logger.warning(f"访问被禁止 (403)，可能是Cookie无效或IP被限制，跳过该时间范围")
                    return []
                elif response.status_code != 200:
                    response.raise_for_status()
                
                # 检查是否有结果
                html = etree.HTML(response.text)
                if html is None:
                    logger.warning(f"无法解析页面，可能是访问受限")
                    retry_count += 1
                    if retry_count < max_retries:
                        self._sleep_with_stop_check(5)  # 等待更长时间后重试
                        if self.stop_flag:
                            return []
                        continue
                    return []
                
                is_empty = html.xpath('//div[@class="card card-no-result s-pt20b40"]')
                if is_empty:
                    logger.info(f"关键词 '{keyword}' 在该时间范围无结果")
                    return []
                
                # 成功获取数据，跳出重试循环
                break
                
            except requests.exceptions.HTTPError as e:
                if hasattr(e, 'response') and e.response and e.response.status_code in [418, 403]:
                    logger.warning(f"请求被拒绝 ({e.response.status_code})，跳过该时间范围")
                    return []
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(f"请求失败，{retry_count * 3}秒后重试...")
                    self._sleep_with_stop_check(retry_count * 3)
                    if self.stop_flag:
                        return []
                else:
                    logger.error(f"请求失败，已达到最大重试次数: {e}")
                    return []
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(f"请求出错，{retry_count * 3}秒后重试: {e}")
                    self._sleep_with_stop_check(retry_count * 3)
                    if self.stop_flag:
                        return []
                else:
                    logger.error(f"请求失败，已达到最大重试次数: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    return []
        
        if response is None or html is None:
            logger.error(f"无法获取数据，已达到最大重试次数")
            return []
        
        # 继续处理成功的响应
        try:
            # 获取页数
            page_count = len(html.xpath('//ul[@class="s-scroll"]/li'))
            
            # 计算时间跨度
            start_date_obj = datetime.strptime(start_str, '%Y-%m-%d-%H')
            end_date_obj = datetime.strptime(end_str, '%Y-%m-%d-%H')
            time_span_days = (end_date_obj - start_date_obj).days
            
            # 如果时间跨度很大（超过90天）且页数较少，直接处理，不细分
            if time_span_days > 90 and page_count < self.further_threshold:
                logger.info(f"关键词 '{keyword}' 该时间范围有 {page_count} 页，时间跨度 {time_span_days} 天，直接处理（不细分）")
                page_weibos = self.parse_page(response.text, keyword)
                all_weibos.extend(page_weibos)
                
                # 获取下一页
                next_url_elem = html.xpath('//a[@class="next"]/@href')
                page_num = 1
                while next_url_elem and not self.stop_flag:
                    self.check_stop_flag()
                    if self.stop_flag:
                        break
                    
                    page_num += 1
                    if self.max_search_count > 0 and self.result_count >= self.max_search_count:
                        break
                    
                    next_url = self.base_url + next_url_elem[0]
                    logger.info(f"获取第 {page_num} 页")
                    
                    # 随机延迟，避免请求过快
                    time.sleep(random.uniform(2, 4))
                    
                    try:
                        next_response = self.session.get(next_url, timeout=15, allow_redirects=True)
                        
                        # 检查状态码
                        if next_response.status_code == 418:
                            logger.warning(f"请求被拒绝 (418)，停止获取下一页")
                            break
                        elif next_response.status_code == 403:
                            logger.warning(f"访问被禁止 (403)，停止获取下一页")
                            break
                        elif next_response.status_code != 200:
                            next_response.raise_for_status()
                        
                        page_weibos = self.parse_page(next_response.text, keyword)
                        all_weibos.extend(page_weibos)
                        
                        next_html = etree.HTML(next_response.text)
                        if next_html is None:
                            logger.warning(f"无法解析页面，停止获取下一页")
                            break
                        next_url_elem = next_html.xpath('//a[@class="next"]/@href')
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code in [418, 403]:
                            logger.warning(f"请求被拒绝 ({e.response.status_code})，停止获取下一页")
                            break
                        logger.error(f"获取下一页时出错: {e}")
                        break
                    except Exception as e:
                        logger.error(f"获取下一页时出错: {e}")
                        break
                
                return all_weibos
            
            if page_count < self.further_threshold:
                # 页数少于阈值，直接解析所有页
                logger.info(f"关键词 '{keyword}' 该时间范围有 {page_count} 页，开始解析")
                page_weibos = self.parse_page(response.text, keyword)
                all_weibos.extend(page_weibos)
                
                # 获取下一页
                next_url_elem = html.xpath('//a[@class="next"]/@href')
                page_num = 1
                while next_url_elem and not self.stop_flag:
                    self.check_stop_flag()
                    if self.stop_flag:
                        break
                    
                    page_num += 1
                    if self.max_search_count > 0 and self.result_count >= self.max_search_count:
                        break
                    
                    next_url = self.base_url + next_url_elem[0]
                    logger.info(f"获取第 {page_num} 页")
                    
                    # 随机延迟，避免请求过快
                    time.sleep(random.uniform(2, 4))
                    
                    try:
                        next_response = self.session.get(next_url, timeout=15, allow_redirects=True)
                        
                        # 检查状态码
                        if next_response.status_code == 418:
                            logger.warning(f"请求被拒绝 (418)，停止获取下一页")
                            break
                        elif next_response.status_code == 403:
                            logger.warning(f"访问被禁止 (403)，停止获取下一页")
                            break
                        elif next_response.status_code != 200:
                            next_response.raise_for_status()
                        
                        page_weibos = self.parse_page(next_response.text, keyword)
                        all_weibos.extend(page_weibos)
                        
                        next_html = etree.HTML(next_response.text)
                        if next_html is None:
                            logger.warning(f"无法解析页面，停止获取下一页")
                            break
                        next_url_elem = next_html.xpath('//a[@class="next"]/@href')
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code in [418, 403]:
                            logger.warning(f"请求被拒绝 ({e.response.status_code})，停止获取下一页")
                            break
                        logger.error(f"获取下一页时出错: {e}")
                        break
                    except Exception as e:
                        logger.error(f"获取下一页时出错: {e}")
                        break
                
                return all_weibos
            else:
                # 页数超过阈值，需要细分时间范围
                logger.info(f"关键词 '{keyword}' 该时间范围有 {page_count} 页（超过阈值 {self.further_threshold}），开始细分时间范围")
                
                # 计算时间范围
                start_date = datetime.strptime(start_str, '%Y-%m-%d-%H')
                end_date = datetime.strptime(end_str, '%Y-%m-%d-%H')
                
                # 如果已经是小时级别（depth=1），不再细分，直接处理
                if depth == 1:
                    logger.info(f"已是小时级别细分，直接处理该时间范围（不再细分）")
                    return self._process_time_range_directly(keyword, start_str, end_str, base_url)
                
                # 按天细分（depth=0），如果天级别仍然超过阈值，会继续细分到小时级别
                if depth == 0:
                    total_days = (end_date - start_date).days
                    
                    # 如果时间跨度超过365天（1年），先按年处理，避免逐天遍历太久
                    if total_days > 365:
                        logger.info(f"时间跨度很大（{total_days} 天，超过1年），先按年处理以提高效率...")
                        current_date = start_date
                        year_count = 0
                        
                        while current_date < end_date and not self.stop_flag:
                            self.check_stop_flag()
                            if self.stop_flag:
                                break
                            
                            # 计算年份的开始和结束
                            year_start = datetime(current_date.year, 1, 1)
                            if year_start < current_date:
                                year_start = current_date
                            
                            year_end = datetime(current_date.year, 12, 31)
                            if year_end > end_date:
                                year_end = end_date
                            
                            year_count += 1
                            logger.info(f"处理第 {year_count} 年: {year_start.strftime('%Y-%m-%d')} 到 {year_end.strftime('%Y-%m-%d')}")
                            
                            year_start_str = year_start.strftime('%Y-%m-%d') + '-0'
                            year_end_str = year_end.strftime('%Y-%m-%d') + '-0'
                            
                            # 递归调用，按年处理
                            year_weibos = self.search_by_time_range(keyword, year_start_str, year_end_str, base_url, depth=depth)
                            all_weibos.extend(year_weibos)
                            
                            if self.max_search_count > 0 and self.result_count >= self.max_search_count:
                                break
                            
                            # 移动到下一年
                            current_date = datetime(current_date.year + 1, 1, 1)
                        
                        logger.info(f"完成 {year_count} 年的细分处理")
                        return all_weibos
                    
                    # 如果时间跨度超过90天，先按月处理，避免逐天遍历太久
                    if total_days > 90:
                        logger.info(f"时间跨度较大（{total_days} 天），先按月处理以提高效率...")
                        current_date = start_date
                        month_count = 0
                        
                        while current_date < end_date and not self.stop_flag:
                            self.check_stop_flag()
                            if self.stop_flag:
                                break
                            
                            # 计算月份的开始和结束
                            month_start = datetime(current_date.year, current_date.month, 1)
                            if month_start < current_date:
                                month_start = current_date
                            
                            # 计算下个月的第一天
                            if current_date.month == 12:
                                next_month = datetime(current_date.year + 1, 1, 1)
                            else:
                                next_month = datetime(current_date.year, current_date.month + 1, 1)
                            
                            month_end = min(next_month - timedelta(days=1), end_date)
                            
                            month_count += 1
                            logger.info(f"处理第 {month_count} 个月: {month_start.strftime('%Y-%m-%d')} 到 {month_end.strftime('%Y-%m-%d')}")
                            
                            month_start_str = month_start.strftime('%Y-%m-%d') + '-0'
                            month_end_str = month_end.strftime('%Y-%m-%d') + '-0'
                            
                            # 递归调用，按月处理
                            month_weibos = self.search_by_time_range(keyword, month_start_str, month_end_str, base_url, depth=depth)
                            all_weibos.extend(month_weibos)
                            
                            if self.max_search_count > 0 and self.result_count >= self.max_search_count:
                                break
                            
                            current_date = next_month
                        
                        logger.info(f"完成 {month_count} 个月的细分处理")
                        return all_weibos
                    
                    # 时间跨度较小（<=90天），按天处理
                    # 但如果天数仍然很多（>30天），先按周处理以提高效率
                    if total_days > 30:
                        logger.info(f"时间跨度 {total_days} 天，先按周处理以提高效率...")
                        current_date = start_date
                        week_count = 0
                        
                        while current_date < end_date and not self.stop_flag:
                            self.check_stop_flag()
                            if self.stop_flag:
                                break
                            
                            week_start = current_date
                            week_end = min(current_date + timedelta(days=7), end_date)
                            
                            week_count += 1
                            logger.info(f"处理第 {week_count} 周: {week_start.strftime('%Y-%m-%d')} 到 {week_end.strftime('%Y-%m-%d')}")
                            
                            week_start_str = week_start.strftime('%Y-%m-%d') + '-0'
                            week_end_str = week_end.strftime('%Y-%m-%d') + '-0'
                            
                            # 递归调用，按周处理
                            week_weibos = self.search_by_time_range(keyword, week_start_str, week_end_str, base_url, depth=depth)
                            all_weibos.extend(week_weibos)
                            
                            if self.max_search_count > 0 and self.result_count >= self.max_search_count:
                                break
                            
                            current_date = week_end
                        
                        logger.info(f"完成 {week_count} 周的细分处理")
                        return all_weibos
                    
                    # 时间跨度很小（<=30天），按天处理
                    current_date = start_date
                    day_count = 0
                    logger.info(f"开始按天细分，共 {total_days} 天")
                    
                    while current_date < end_date and not self.stop_flag:
                        self.check_stop_flag()
                        if self.stop_flag:
                            break
                        
                        day_start = current_date.strftime('%Y-%m-%d') + '-0'
                        current_date = current_date + timedelta(days=1)
                        day_end = current_date.strftime('%Y-%m-%d') + '-0'
                        
                        day_count += 1
                        if day_count % 10 == 0 or day_count == 1:
                            logger.info(f"处理第 {day_count}/{total_days} 天: {day_start} 到 {day_end}")
                        
                        # 递归调用，depth+1表示进入下一级细分（小时级别）
                        # 如果小时级别仍然超过阈值，会调用 _process_time_range_directly 直接处理
                        day_weibos = self.search_by_time_range(keyword, day_start, day_end, base_url, depth=depth+1)
                        all_weibos.extend(day_weibos)
                        
                        if self.max_search_count > 0 and self.result_count >= self.max_search_count:
                            break
                    
                    logger.info(f"完成 {day_count} 天的细分处理")
                    return all_weibos
                else:
                    # 其他情况（不应该到达这里），直接处理
                    logger.warning(f"意外的深度值 {depth}，直接处理")
                    return self._process_time_range_directly(keyword, start_str, end_str, base_url)
                
        except Exception as e:
            logger.error(f"搜索时间范围时出错: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def save_weibos(self, weibo_list, keyword):
        """保存微博数据"""
        if not weibo_list:
            return
        
        # 确保输出目录存在
        keyword_dir = os.path.join(self.output_dir, keyword)
        if not os.path.exists(keyword_dir):
            os.makedirs(keyword_dir)
        
        # 保存为CSV
        if 'csv' in self.write_mode:
            csv_path = os.path.join(keyword_dir, f"{keyword}_posts.csv")
            file_exists = os.path.exists(csv_path)
            
            with open(csv_path, 'a', encoding='utf-8-sig', newline='') as f:
                import csv as csv_module
                writer = csv_module.writer(f)
                
                if not file_exists:
                    # 写入表头
                    header = [
                        'id', 'bid', 'user_id', '用户昵称', '微博正文', '头条文章url',
                        '发布位置', '艾特用户', '话题', '转发数', '评论数', '点赞数', '发布时间',
                        '发布工具', '微博图片url', '微博视频url', 'retweet_id', 'ip', 'user_authentication',
                        '会员类型', '会员等级', '帖子链接'
                    ]
                    writer.writerow(header)
                
                # 写入数据
                for weibo in weibo_list:
                    # 将ID字段转换为字符串并添加制表符，避免CSV使用科学计数法
                    weibo_id = weibo.get('id', '')
                    user_id = weibo.get('user_id', '')
                    retweet_id = weibo.get('retweet_id', '')
                    writer.writerow([
                        '\t' + str(weibo_id) if weibo_id else '',
                        weibo.get('bid', ''),
                        '\t' + str(user_id) if user_id else '',
                        weibo.get('screen_name', ''),
                        weibo.get('text', ''),
                        weibo.get('article_url', ''),
                        weibo.get('location', ''),
                        weibo.get('at_users', ''),
                        weibo.get('topics', ''),
                        weibo.get('reposts_count', '0'),
                        weibo.get('comments_count', '0'),
                        weibo.get('attitudes_count', '0'),
                        weibo.get('created_at', ''),
                        weibo.get('source', ''),
                        weibo.get('pics', ''),
                        weibo.get('video_url', ''),
                        '\t' + str(retweet_id) if retweet_id else '',
                        weibo.get('ip', ''),
                        weibo.get('user_authentication', '普通用户'),
                        weibo.get('vip_type', '非会员'),
                        weibo.get('vip_level', 0),
                        weibo.get('weibo_url', '')
                    ])
            
            logger.info(f"已保存 {len(weibo_list)} 条微博到 {csv_path}")
        
        # 保存为JSON
        if 'json' in self.write_mode:
            json_path = os.path.join(keyword_dir, f"{keyword}_posts.json")
            existing_data = []
            
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    try:
                        existing_data = json.load(f)
                    except:
                        existing_data = []
            
            existing_data.extend(weibo_list)
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存 {len(weibo_list)} 条微博到 {json_path}")
    
    def _process_time_range_directly(self, keyword, start_str, end_str, base_url):
        """直接处理时间范围，不再细分（用于小时级别或达到最大深度时）"""
        all_weibos = []
        url = base_url + self.weibo_type
        url += self.contain_type
        url += '&timescope=custom:{}:{}'.format(start_str, end_str)
        
        try:
            logger.info(f"直接处理时间范围: {start_str} 到 {end_str}")
            time.sleep(random.uniform(1, 3))
            
            response = self.session.get(url, timeout=15, allow_redirects=True)
            
            if response.status_code == 418 or response.status_code == 403:
                logger.warning(f"请求被拒绝 ({response.status_code})，跳过该时间范围")
                return []
            elif response.status_code != 200:
                response.raise_for_status()
            
            html = etree.HTML(response.text)
            if html is None:
                return []
            
            # 直接解析所有页，不再检查页数
            page_weibos = self.parse_page(response.text, keyword)
            all_weibos.extend(page_weibos)
            
            # 获取下一页
            next_url_elem = html.xpath('//a[@class="next"]/@href')
            page_num = 1
            while next_url_elem and not self.stop_flag:
                self.check_stop_flag()
                if self.stop_flag:
                    break
                
                page_num += 1
                if self.max_search_count > 0 and self.result_count >= self.max_search_count:
                    break
                
                next_url = self.base_url + next_url_elem[0]
                logger.info(f"获取第 {page_num} 页")
                time.sleep(random.uniform(2, 4))
                
                try:
                    next_response = self.session.get(next_url, timeout=15, allow_redirects=True)
                    
                    if next_response.status_code == 418 or next_response.status_code == 403:
                        logger.warning(f"请求被拒绝 ({next_response.status_code})，停止获取下一页")
                        break
                    elif next_response.status_code != 200:
                        next_response.raise_for_status()
                    
                    page_weibos = self.parse_page(next_response.text, keyword)
                    all_weibos.extend(page_weibos)
                    
                    next_html = etree.HTML(next_response.text)
                    if next_html is None:
                        break
                    next_url_elem = next_html.xpath('//a[@class="next"]/@href')
                except Exception as e:
                    logger.error(f"获取下一页时出错: {e}")
                    break
            
            return all_weibos
            
        except Exception as e:
            logger.error(f"处理时间范围时出错: {e}")
            return []
    
    def download_one_file(self, url, file_path, file_type, weibo_id):
        """下载单个文件（图片或视频）"""
        try:
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.info(f"已下载 {file_type}: {os.path.basename(file_path)}")
        except Exception as e:
            logger.warning(f"下载 {file_type} 失败 {url}: {e}")
    
    def download_media(self, weibo_list, keyword):
        """下载微博的图片和视频"""
        keyword_dir = os.path.join(self.output_dir, keyword)
        
        # 统计需要下载的文件数量
        total_pics = 0
        total_videos = 0
        for weibo in weibo_list:
            retweet_id = weibo.get('retweet_id', '')
            is_retweet = bool(retweet_id)
            pics = weibo.get('pics', '')
            video_url = weibo.get('video_url', '')
            
            if pics:
                if (is_retweet and self.retweet_pic_download) or (not is_retweet and self.original_pic_download):
                    if ',' in pics:
                        total_pics += len(pics.split(','))
                    else:
                        total_pics += 1
            
            if video_url:
                if (is_retweet and self.retweet_video_download) or (not is_retweet and self.original_video_download):
                    total_videos += 1
        
        # 输出下载开始日志
        if total_pics > 0 or total_videos > 0:
            logger.info(f"开始下载关键词 '{keyword}' 的媒体文件: 图片 {total_pics} 张, 视频 {total_videos} 个")
        
        downloaded_pics = 0
        downloaded_videos = 0
        
        for weibo in weibo_list:
            if self.stop_flag:
                break
            
            weibo_id = str(weibo.get('id', ''))
            retweet_id = weibo.get('retweet_id', '')
            is_retweet = bool(retweet_id)
            
            # 下载图片
            pics = weibo.get('pics', '')
            if pics:
                if is_retweet and self.retweet_pic_download:
                    pic_dir = os.path.join(keyword_dir, 'images')
                    if ',' in pics:
                        pic_urls = pics.split(',')
                    else:
                        pic_urls = [pics]
                    for i, pic_url in enumerate(pic_urls):
                        if pic_url.strip():
                            file_prefix = weibo.get('created_at', '')[:10].replace('-', '') + '_' + weibo_id
                            file_suffix = '.jpg'
                            if '.' in pic_url:
                                file_suffix = '.' + pic_url.split('.')[-1].split('?')[0]
                            file_name = f"{file_prefix}_{i+1}{file_suffix}"
                            file_path = os.path.join(pic_dir, file_name)
                            self.download_one_file(pic_url.strip(), file_path, 'img', weibo_id)
                            downloaded_pics += 1
                            downloaded_pics += 1
                elif not is_retweet and self.original_pic_download:
                    pic_dir = os.path.join(keyword_dir, 'images')
                    if ',' in pics:
                        pic_urls = pics.split(',')
                    else:
                        pic_urls = [pics]
                    for i, pic_url in enumerate(pic_urls):
                        if pic_url.strip():
                            file_prefix = weibo.get('created_at', '')[:10].replace('-', '') + '_' + weibo_id
                            file_suffix = '.jpg'
                            if '.' in pic_url:
                                file_suffix = '.' + pic_url.split('.')[-1].split('?')[0]
                            file_name = f"{file_prefix}_{i+1}{file_suffix}"
                            file_path = os.path.join(pic_dir, file_name)
                            self.download_one_file(pic_url.strip(), file_path, 'img', weibo_id)
                            downloaded_pics += 1
            
            # 下载视频
            video_url = weibo.get('video_url', '')
            if video_url:
                if is_retweet and self.retweet_video_download:
                    video_dir = os.path.join(keyword_dir, 'videos')
                    file_prefix = weibo.get('created_at', '')[:10].replace('-', '') + '_' + weibo_id
                    file_suffix = '.mp4'
                    if video_url.endswith('.mov'):
                        file_suffix = '.mov'
                    file_name = f"{file_prefix}{file_suffix}"
                    file_path = os.path.join(video_dir, file_name)
                    self.download_one_file(video_url, file_path, 'video', weibo_id)
                    downloaded_videos += 1
                elif not is_retweet and self.original_video_download:
                    video_dir = os.path.join(keyword_dir, 'videos')
                    file_prefix = weibo.get('created_at', '')[:10].replace('-', '') + '_' + weibo_id
                    file_suffix = '.mp4'
                    if video_url.endswith('.mov'):
                        file_suffix = '.mov'
                    file_name = f"{file_prefix}{file_suffix}"
                    file_path = os.path.join(video_dir, file_name)
                    self.download_one_file(video_url, file_path, 'video', weibo_id)
                    downloaded_videos += 1
        
        # 输出下载完成日志
        if total_pics > 0 or total_videos > 0:
            logger.info(f"关键词 '{keyword}' 媒体文件下载完成: 图片 {downloaded_pics}/{total_pics} 张, 视频 {downloaded_videos}/{total_videos} 个")
            if downloaded_pics > 0:
                logger.info(f"图片保存路径: {os.path.join(keyword_dir, 'images')}")
            if downloaded_videos > 0:
                logger.info(f"视频保存路径: {os.path.join(keyword_dir, 'videos')}")
    
    def download_comments(self, weibo_list, keyword):
        """下载微博评论"""
        if not self.download_comment or self.comment_max_download_count <= 0:
            return
        
        keyword_dir = os.path.join(self.output_dir, keyword)
        comments_csv_path = os.path.join(keyword_dir, f"{keyword}_comments.csv")
        file_exists = os.path.exists(comments_csv_path)
        
        # 初始化评论计数器
        if not hasattr(self, '_comment_counters'):
            self._comment_counters = {}
        
        for weibo in weibo_list:
            if self.stop_flag:
                break
            
            weibo_id = str(weibo.get('id', ''))
            comments_count = int(weibo.get('comments_count', '0') or '0')
            
            if comments_count <= 0:
                continue
            
            # 检查是否已达到限制
            if weibo_id not in self._comment_counters:
                self._comment_counters[weibo_id] = 0
            
            if self._comment_counters[weibo_id] >= self.comment_max_download_count:
                continue
            
            try:
                # 获取评论
                url = f"https://m.weibo.cn/api/comments/show?id={weibo_id}&page=1"
                response = self.session.get(url, timeout=10)
                if response.status_code != 200:
                    continue
                
                data = response.json()
                if not data or not data.get('ok'):
                    continue
                
                comments_data = data.get('data', {})
                comments = comments_data.get('data', [])
                
                if not comments:
                    continue
                
                # 保存评论到CSV
                with open(comments_csv_path, 'a', encoding='utf-8-sig', newline='') as f:
                    import csv as csv_module
                    writer = csv_module.writer(f)
                    
                    if not file_exists:
                        # 写入表头
                        header = ['id', 'weibo_id', 'created_at', 'user_id', 'user_screen_name', 'text', 'pic_url', 'like_count']
                        writer.writerow(header)
                        file_exists = True
                    
                    # 写入评论
                    written = 0
                    for comment in comments:
                        if self._comment_counters[weibo_id] >= self.comment_max_download_count:
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
                        written += 1
                        self._comment_counters[weibo_id] += 1
                    
                    if written > 0:
                        logger.info(f"已保存 {written} 条评论到 {comments_csv_path} (微博ID: {weibo_id})")
                
                # 继续获取更多页的评论
                max_page = comments_data.get('max', 0)
                if max_page > 1:
                    for page in range(2, min(max_page + 1, 10)):  # 最多获取10页
                        if self._comment_counters[weibo_id] >= self.comment_max_download_count:
                            break
                        
                        time.sleep(random.uniform(1, 2))
                        url = f"https://m.weibo.cn/api/comments/show?id={weibo_id}&page={page}"
                        response = self.session.get(url, timeout=10)
                        if response.status_code != 200:
                            break
                        
                        data = response.json()
                        if not data or not data.get('ok'):
                            break
                        
                        comments_data = data.get('data', {})
                        comments = comments_data.get('data', [])
                        if not comments:
                            break
                        
                        with open(comments_csv_path, 'a', encoding='utf-8-sig', newline='') as f:
                            writer = csv_module.writer(f)
                            for comment in comments:
                                if self._comment_counters[weibo_id] >= self.comment_max_download_count:
                                    break
                                
                                comment_id = comment.get('id', '')
                                user = comment.get('user', {})
                                user_id = user.get('id', '') if isinstance(user, dict) else ''
                                screen_name = user.get('screen_name', '') if isinstance(user, dict) else ''
                                text = comment.get('text', '')
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
                                self._comment_counters[weibo_id] += 1
                        
                        if self._comment_counters[weibo_id] >= self.comment_max_download_count:
                            break
                            
            except Exception as e:
                logger.warning(f"下载评论失败 (微博ID: {weibo_id}): {e}")
                continue
    
    def check_date_range_has_data(self, keyword, base_url, start_date, end_date):
        """检查指定日期范围是否有数据"""
        start_str = start_date.strftime('%Y-%m-%d') + '-0'
        end_str = end_date.strftime('%Y-%m-%d') + '-0'
        url = base_url + self.weibo_type + self.contain_type
        url += '&timescope=custom:{}:{}'.format(start_str, end_str)
        
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            if response.status_code in [418, 403]:
                return None  # 请求被拒绝
            if response.status_code == 200:
                html = etree.HTML(response.text)
                if html:
                    is_empty = html.xpath('//div[@class="card card-no-result s-pt20b40"]')
                    return not is_empty  # True表示有数据，False表示无数据
        except:
            pass
        return None  # 出错返回None
    
    def find_earliest_date_with_data(self, keyword, base_url, start_date, end_date):
        """
        快速定位最早有数据的日期（在指定时间范围内）
        使用分层回溯策略：先按年快速定位，再按月精确到月份
        
        Args:
            keyword: 搜索关键词
            base_url: 基础URL
            start_date: 起始日期（从这个日期开始向前查找）
            end_date: 结束日期
            
        Returns:
            datetime: 最早有数据的日期（月份的第一天），如果没找到则返回start_date
        """
        logger.info(f"开始快速定位最早有数据的日期（从 {start_date.strftime('%Y-%m-%d')} 开始）...")
        
        # 第一步：快速按年回溯，找到最早有数据的年份
        current_end = end_date
        min_date = start_date  # 从用户设置的起始日期开始，而不是从2010年
        earliest_year = None
        
        logger.info("第一步：按年回溯，快速定位最早有数据的年份...")
        while current_end.year >= min_date.year:
            self.check_stop_flag()
            if self.stop_flag:
                return None
            
            # 检查当前年份
            year_start = datetime(current_end.year, 1, 1)
            if year_start < min_date:
                year_start = min_date
            
            year_end = datetime(current_end.year, 12, 31)
            if year_end > current_end:
                year_end = current_end
            
            logger.info(f"检查年份: {current_end.year}")
            has_data = self.check_date_range_has_data(keyword, base_url, year_start, year_end)
            
            if has_data is None:
                logger.warning("请求被拒绝，停止回溯")
                break
            
            if has_data:
                earliest_year = current_end.year
                logger.info(f"年份 {current_end.year} 有数据")
                current_end = datetime(current_end.year - 1, 12, 31)
            else:
                logger.info(f"年份 {current_end.year} 无数据")
                break
            
            time.sleep(random.uniform(0.3, 0.8))
            
            if current_end < min_date:
                break
        
        if earliest_year is None:
            logger.info(f"在时间范围内未找到任何数据，使用起始日期: {start_date.strftime('%Y-%m-%d')}")
            return start_date  # 如果没找到，返回用户设置的起始日期
        
        # 第二步：在找到的年份内，按月查找最早有数据的月份
        logger.info(f"第二步：在 {earliest_year} 年内，按月查找最早有数据的月份...")
        
        earliest_month = None
        # 从1月到12月依次检查
        for month in range(1, 13):
            self.check_stop_flag()
            if self.stop_flag:
                return None
            
            # 计算月份的开始和结束日期
            if month == 12:
                month_start = datetime(earliest_year, month, 1)
                month_end = datetime(earliest_year + 1, 1, 1) - timedelta(days=1)
            else:
                month_start = datetime(earliest_year, month, 1)
                month_end = datetime(earliest_year, month + 1, 1) - timedelta(days=1)
            
            if month_end > end_date:
                month_end = end_date
            
            logger.info(f"检查月份: {month_start.strftime('%Y-%m')}")
            has_data = self.check_date_range_has_data(keyword, base_url, month_start, month_end)
            time.sleep(random.uniform(0.3, 0.8))
            
            if has_data:
                earliest_month = month
                logger.info(f"找到最早有数据的月份: {month_start.strftime('%Y-%m')}")
                break
        
        if earliest_month is None:
            # 如果按月检查失败，使用年份的第一天
            logger.info(f"无法确定具体月份，使用年份开始: {earliest_year}-01-01")
            return datetime(earliest_year, 1, 1)
        
        earliest_date = datetime(earliest_year, earliest_month, 1)
        logger.info(f"定位到最早有数据的日期: {earliest_date.strftime('%Y-%m-%d')}")
        return earliest_date
    
    def search_keyword(self, keyword):
        """搜索单个关键词"""
        logger.info(f"开始搜索关键词: {keyword}")
        
        # URL编码关键词
        # 如果是话题格式，需要特殊处理
        if len(keyword) > 2 and keyword[0] == '#' and keyword[-1] == '#':
            encoded_keyword = '%23' + quote(keyword[1:-1]) + '%23'
        else:
            encoded_keyword = quote(keyword)
        
        base_url = f'{self.base_url}/weibo?q={encoded_keyword}'
        
        # 检查是否需要快速定位最早日期
        # 如果时间跨度超过7天，就启用快速定位（在当前时间范围内找到最早有数据的日期）
        time_span_days = (self.end_date - self.start_date).days
        need_fast_locate = False
        
        # 判断条件：
        # 1. 时间跨度超过7天，启用快速定位（在时间范围内找到最早有数据的日期）
        # 2. 或者配置中明确设置了需要从最早开始（since_date为"1900-01-01"或空）
        if time_span_days > 7:
            need_fast_locate = True
            logger.info(f"检测到时间跨度较大（{time_span_days}天），将使用快速定位策略找到最早有数据的日期")
        elif self.original_since_date == "1900-01-01" or self.original_since_date == "" or str(self.original_since_date).strip() == "":
            need_fast_locate = True
            logger.info("检测到起始日期为空或设置为'1900-01-01'，将使用快速定位策略找到最早有数据的日期")
        
        # 如果需要快速定位，先找到最早有数据的日期（在时间范围内）
        if need_fast_locate:
            logger.info("=" * 60)
            logger.info(f"开始快速定位最早有数据的日期（时间范围: {self.start_date.strftime('%Y-%m-%d')} 到 {self.end_date.strftime('%Y-%m-%d')}）...")
            logger.info("=" * 60)
            earliest_date = self.find_earliest_date_with_data(keyword, base_url, self.start_date, self.end_date)
            if earliest_date and earliest_date != self.start_date:
                # 使用定位到的日期作为起始日期
                self.start_date = earliest_date
                new_time_span = (self.end_date - earliest_date).days
                logger.info("=" * 60)
                logger.info(f"快速定位完成！最早有数据的日期: {earliest_date.strftime('%Y-%m-%d')}")
                logger.info(f"新的搜索时间范围: {earliest_date.strftime('%Y-%m-%d')} 到 {self.end_date.strftime('%Y-%m-%d')} (共 {new_time_span} 天)")
                logger.info("=" * 60)
            elif earliest_date == self.start_date:
                logger.info(f"在时间范围内未找到数据，使用原始起始日期: {self.start_date.strftime('%Y-%m-%d')}")
        
        # 构建时间范围
        start_str = self.start_date.strftime('%Y-%m-%d') + '-0'
        end_date_plus_one = self.end_date + timedelta(days=1)
        end_str = end_date_plus_one.strftime('%Y-%m-%d') + '-0'
        
        final_time_span = (self.end_date - self.start_date).days
        logger.info(f"开始搜索，时间范围: {self.start_date.strftime('%Y-%m-%d')} 到 {self.end_date.strftime('%Y-%m-%d')} (共 {final_time_span} 天)")
        
        # 执行搜索（搜索过程中会自动保存每页数据）
        # depth=0 表示从最顶层开始，会按天细分，如果天级别超过阈值，会继续按小时细分
        all_weibos = self.search_by_time_range(keyword, start_str, end_str, base_url, depth=0)
        
        # 最终统计
        if all_weibos:
            logger.info(f"关键词 '{keyword}' 搜索完成，共获取 {len(all_weibos)} 条微博")
        else:
            logger.info(f"关键词 '{keyword}' 搜索完成，未获取到数据")
        
        return all_weibos


def search_by_keywords(config):
    """
    根据关键词搜索微博
    
    Args:
        config: 配置字典，包含：
            - search_keywords: 搜索关键词列表
            - max_search_count: 最大搜索条数
            - start_date: 开始日期 (yyyy-mm-dd)
            - end_date: 结束日期 (yyyy-mm-dd)
            - cookie: Cookie字符串
            - 其他配置项
    """
    search_keywords = config.get("search_keywords", [])
    if not search_keywords:
        logger.error("未设置搜索关键词")
        return
    
    if isinstance(search_keywords, str):
        search_keywords = [kw.strip() for kw in search_keywords.split(",") if kw.strip()]
    
    # 创建搜索器
    searcher = WeiboKeywordSearcher(config)
    
    # 为每个关键词执行搜索
    for keyword in search_keywords:
        searcher.check_stop_flag()
        if searcher.stop_flag:
            logger.info("检测到停止标志，停止搜索")
            break
        
        try:
            searcher.search_keyword(keyword)
        except Exception as e:
            logger.error(f"搜索关键词 '{keyword}' 时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    logger.info(f"关键词搜索完成，共获取 {searcher.result_count} 条微博")


def main():
    """主函数，用于测试"""
    import json
    
    if len(sys.argv) < 2:
        print("用法: python keyword_search.py <config.json>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    search_by_keywords(config)


if __name__ == "__main__":
    main()

