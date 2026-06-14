#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微博爬虫补丁模块
用于修改weibo.py的行为，实现：
1. 每页保存数据（而不是每20页）
2. 支持停止标志检查
"""

import weibo
from datetime import datetime
from time import sleep
import random
from tqdm import tqdm


# 全局停止标志
_stop_flag = False


def set_stop_flag(value):
    """设置停止标志"""
    global _stop_flag
    _stop_flag = value


def get_stop_flag():
    """获取停止标志"""
    return _stop_flag


def patched_get_pages(self):
    """修改后的get_pages方法，每页保存并支持停止"""
    try:
        # 用户id不可用
        if self.get_user_info() != 0:
            return
        weibo.logger.info("准备搜集 {} 的微博".format(self.user["screen_name"]))
        if weibo.const.MODE == "append" and (
            "first_crawler" not in self.__dict__ or self.first_crawler is False
        ):
            # 本次运行的某用户首次抓取，用于标记最新的微博id
            self.first_crawler = True
            weibo.const.CHECK_COOKIE["GUESS_PIN"] = True
        since_date = datetime.strptime(self.user_config["since_date"], weibo.DTFORMAT)
        today = datetime.today()
        if since_date <= today:    # since_date 若为未来则无需执行
            page_count = self.get_page_count()
            wrote_count = 0
            page1 = 0
            random_pages = random.randint(1, 5)
            self.start_date = datetime.now().strftime(weibo.DTFORMAT)
            pages = range(self.start_page, page_count + 1)
            for page in tqdm(pages, desc="Progress"):
                # 在开始新页之前检查停止标志
                if get_stop_flag():
                    weibo.logger.info("检测到停止请求，停止爬取")
                    # 保存当前已爬取的数据
                    if self.got_count > wrote_count:
                        self.write_data(wrote_count)
                    # 标记已停止
                    self._crawl_stopped = True
                    break
                
                # 爬取当前页
                is_end = self.get_one_page(page)
                
                # 每页爬取完成后立即保存数据（修改：从每20页改为每页）
                if self.got_count > wrote_count:
                    self.write_data(wrote_count)
                    wrote_count = self.got_count
                
                if is_end:
                    break
                
                # 在保存后再次检查停止标志
                if get_stop_flag():
                    weibo.logger.info("检测到停止请求，停止爬取")
                    # 标记已停止
                    self._crawl_stopped = True
                    break

                # 通过加入随机等待避免被限制。爬虫速度过快容易被系统限制(一段时间后限
                # 制会自动解除)，加入随机等待模拟人的操作，可降低被系统限制的风险。默
                # 认是每爬取1到5页随机等待6到10秒，如果仍然被限，可适当增加sleep时间
                if (page - page1) % random_pages == 0 and page < page_count:
                    # 分片sleep以便在等待期间检查停止标志
                    sleep_duration = random.randint(6, 10)
                    remaining = sleep_duration
                    while remaining > 0:
                        if get_stop_flag():
                            weibo.logger.info("检测到停止请求，停止爬取")
                            # 标记已停止
                            self._crawl_stopped = True
                            break
                        sleep_time = min(1.0, remaining)  # 每次最多sleep 1秒
                        sleep(sleep_time)
                        remaining -= sleep_time
                    
                    if get_stop_flag():
                        weibo.logger.info("检测到停止请求，停止爬取")
                        # 标记已停止
                        self._crawl_stopped = True
                        break
                    
                    page1 = page
                    random_pages = random.randint(1, 5)
            
            # 最后再保存一次，确保所有数据都已保存
            if self.got_count > wrote_count:
                self.write_data(wrote_count)
                
        # 检查是否因为停止请求而退出
        if hasattr(self, '_crawl_stopped') and self._crawl_stopped:
            weibo.logger.info("爬取已停止，共爬取%d条微博", self.got_count)
        else:
            weibo.logger.info("微博爬取完成，共爬取%d条微博", self.got_count)
    except Exception as e:
        weibo.logger.exception(e)


def apply_patch():
    """应用补丁到weibo模块"""
    # 替换get_pages方法
    weibo.Weibo.get_pages = patched_get_pages
    weibo.logger.info("已应用补丁：每页保存数据，支持停止标志")


def remove_patch():
    """移除补丁（恢复原始方法）"""
    # 注意：这里无法完全恢复，因为原始方法已经被替换
    # 如果需要恢复，需要重新导入模块
    pass

