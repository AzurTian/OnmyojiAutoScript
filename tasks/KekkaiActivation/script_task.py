# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import time

import random
import re
from cached_property import cached_property
from datetime import datetime, timedelta
from module.atom.click import RuleClick

from module.base.timer import Timer
from module.atom.image_grid import ImageGrid
from module.atom.image import RuleImage
from module.base.utils import point2str
from module.logger import logger
from module.exception import TaskEnd, GameStuckError
from tasks.KekkaiUtilize.page import page_guild_realm, page_guild_realm_growth, page_guild_card

from tasks.KekkaiUtilize.script_task import ScriptTask as KU
from tasks.KekkaiUtilize.utils import CardClass
from tasks.KekkaiActivation.assets import KekkaiActivationAssets
from tasks.KekkaiActivation.utils import parse_rule
from tasks.KekkaiActivation.config import ActivationConfig, CardType, CardStar
from tasks.Utils.config_enum import ShikigamiClass
from tasks.GameUi.page import page_main, page_guild

""" 结界挂卡 """
class ScriptTask(KU, KekkaiActivationAssets):

    def run(self):
        con = self.config.kekkai_activation.activation_config
        # 进入寮结界
        self.goto_page(page_guild_realm)

        if con.exchange_before:
            self.check_max_lv(con.shikigami_class, con.auto_fill)
        # 收取经验
        self.harvest_card()
        # 开始挂卡
        self.run_activation(con)
        self.goto_page(page_guild_realm)

        if con.exchange_max:
            self.check_max_lv(con.shikigami_class, con.auto_fill)
        self.goto_page(page_main)

        raise TaskEnd('KekkaiActivation')

    @cached_property
    def dict_card_image(self) -> dict:
        match_targets = {
            CardClass.TAIKO6: self.I_CARDS_KAIKO_6,
            CardClass.TAIKO5: self.I_CARDS_KAIKO_5,
            CardClass.TAIKO4: self.I_CARDS_KAIKO_4,
            CardClass.TAIKO3: self.I_CARDS_KAIKO_3,
            CardClass.FISH6: self.I_CARDS_FISH_6,
            CardClass.FISH5: self.I_CARDS_FISH_5,
            CardClass.FISH4: self.I_CARDS_FISH_4,
            CardClass.FISH3: self.I_CARDS_FISH_3,
            CardClass.MOON6: self.I_CARDS_MOON_6,
            CardClass.MOON5: self.I_CARDS_MOON_5,
            CardClass.MOON4: self.I_CARDS_MOON_4,
            CardClass.MOON3: self.I_CARDS_MOON_3,
            CardClass.MOON2: self.I_CARDS_MOON_2,
            CardClass.MOON1: self.I_CARDS_MOON_1
        }
        return match_targets

    @cached_property
    def dict_image_card(self) -> dict:
        return {v: k for k, v in self.dict_card_image.items()}
    
    @cached_property
    def star_mapping(self) -> dict:
        """根据配置的星级返回目标卡和干扰卡的图片列表"""
        card_star = self.config.kekkai_activation.activation_config.card_star
        
        if card_star == CardStar.SIX:
            # 六星模式：所有卡都是目标卡，无干扰卡
            return {
                'target_images': {
                    CardType.TAIKO: [self.I_CARDS_KAIKO_6, self.I_CARDS_KAIKO_5, 
                                    self.I_CARDS_KAIKO_4, self.I_CARDS_KAIKO_3],
                    CardType.FISH: [self.I_CARDS_FISH_6, self.I_CARDS_FISH_5,
                                self.I_CARDS_FISH_4, self.I_CARDS_FISH_3]
                },
                'higher_images': {
                    CardType.TAIKO: [],  # 无干扰卡
                    CardType.FISH: []     # 无干扰卡
                }
            }
        elif card_star == CardStar.FIVE:
            # 五星模式：目标卡=5,4,3星，干扰卡=6星
            return {
                'target_images': {
                    CardType.TAIKO: [self.I_CARDS_KAIKO_5, self.I_CARDS_KAIKO_4, self.I_CARDS_KAIKO_3],
                    CardType.FISH: [self.I_CARDS_FISH_5, self.I_CARDS_FISH_4, self.I_CARDS_FISH_3]
                },
                'higher_images': {
                    CardType.TAIKO: [self.I_CARDS_KAIKO_6],
                    CardType.FISH: [self.I_CARDS_FISH_6]
                }
            }
        else:
            logger.error(f'不支持的星级配置: {card_star}')
            raise ValueError(f'不支持的星级配置: {card_star}')

    @cached_property
    def order_targets(self) -> ImageGrid:
        rule = self.config.kekkai_activation.activation_config.card_type
        if rule == CardType.TAIKO:
            return ImageGrid([self.I_CARDS_KAIKO_6, self.I_CARDS_KAIKO_5])
        elif rule == CardType.FISH:
            return ImageGrid([self.I_CARDS_FISH_6, self.I_CARDS_FISH_5])
        else:
            logger.error('Unknown utilize rule')
            raise ValueError('Unknown utilize rule')
            
    def _collect_cards_by_image(self, image_obj, card_type_label, threshold=None):
        """
        收集指定图片对象的所有匹配位置
        :param image_obj: RuleImage对象
        :param card_type_label: 卡片类型标签（如'目标卡'、'干扰卡'）
        :param threshold: 匹配阈值，默认使用image_obj.threshold
        :return: 卡片列表，每个元素为(类型, 图片对象, 中心x, 中心y, 阈值)
        """
        if threshold is None:
            threshold = image_obj.threshold
        
        cards = []
        # 使用match_all_any获取去重后的匹配位置
        matches = image_obj.match_all_any(self.device.image, threshold=threshold, nms_threshold=0.3)
        
        for match in matches:
            # 解析匹配结果格式 (confidence, x, y, w, h)
            if len(match) == 5:
                confidence, x, y, w, h = match
                center_x = x + w / 2
                center_y = y + h / 2
            elif len(match) == 4:
                x, y, w, h = match
                center_x = x + w / 2
                center_y = y + h / 2
            else:
                continue
            
            cards.append((card_type_label, image_obj, center_x, center_y, threshold))
        
        return cards

    def _collect_all_cards(self, target_images, higher_images, card_star):
        """
        收集当前页面所有卡片（目标卡和干扰卡）
        :param target_images: 目标卡图片列表
        :param higher_images: 干扰卡图片列表
        :param card_star: 当前星级模式
        :return: 卡片列表，已按y坐标排序
        """
        all_cards = []
        
        # 收集干扰卡
        for higher_image in higher_images:
            cards = self._collect_cards_by_image(higher_image, '干扰卡')
            all_cards.extend(cards)
        
        # 收集目标卡
        for target_image in target_images:
            cards = self._collect_cards_by_image(target_image, '目标卡')
            all_cards.extend(cards)
        
        # 按y坐标排序
        all_cards.sort(key=lambda x: x[3])  # 按center_y排序
        
        return all_cards

    def _extract_ocr_results(self, results, check_card):
        """
        从OCR结果中提取有效信息
        :param results: OCR识别结果列表
        :param check_card: 要检查的卡片类型关键词（"勾玉"或"体力"）
        :return: OCR信息列表，每个元素为字典
        """
        ocr_list = []
        for result in results:
            if check_card in result.ocr_text:
                # 计算OCR结果的中心位置
                ocr_center_x = result.box[0][0] + (result.box[1][0] - result.box[0][0]) / 2
                ocr_center_y = result.box[0][1] + (result.box[2][1] - result.box[0][1]) / 2
                ocr_center_x += self.O_CHECK_CARD_NUMBER.roi[0]
                ocr_center_y += self.O_CHECK_CARD_NUMBER.roi[1]
                
                # 提取数字
                numbers = [int(num) for num in re.findall(r'\d+', result.ocr_text)]
                if numbers:
                    ocr_list.append({
                        'text': result.ocr_text,
                        'value': numbers[0],
                        'center_x': ocr_center_x,
                        'center_y': ocr_center_y,
                        'result': result
                    })
        
        # 按y坐标排序
        ocr_list.sort(key=lambda x: x['center_y'])
        return ocr_list

    def _perform_regular_ocr_check(self, results, target_images, higher_images, card_star, 
                                has_ever_seen_target, min_card_num, check_card):
        """
        执行常规OCR检查
        :param results: OCR识别结果
        :param target_images: 目标卡图片列表
        :param higher_images: 干扰卡图片列表
        :param card_star: 当前星级模式
        :param has_ever_seen_target: 是否见过目标卡
        :param min_card_num: 最低收益阈值
        :param check_card: 卡片类型关键词
        :return: 过滤后的OCR结果列表
        """
        filtered_results = []
        
        if card_star == CardStar.FIVE and not has_ever_seen_target:
            # 五星模式，从未见过目标卡：只处理目标卡
            # 收集当前页面所有的目标卡位置
            target_card_positions = []
            for target_image in target_images:
                if self.appear(target_image):
                    target_area = target_image.roi_front
                    target_center_x = target_area[0] + target_area[2] / 2
                    target_center_y = target_area[1] + target_area[3] / 2
                    target_card_positions.append((target_center_x, target_center_y, target_image))
            
            for result in results:
                if check_card in result.ocr_text:
                    # 计算OCR结果的中心位置
                    ocr_center_x = result.box[0][0] + (result.box[1][0] - result.box[0][0]) / 2
                    ocr_center_y = result.box[0][1] + (result.box[2][1] - result.box[0][1]) / 2
                    ocr_center_x += self.O_CHECK_CARD_NUMBER.roi[0]
                    ocr_center_y += self.O_CHECK_CARD_NUMBER.roi[1]
                    
                    # 检查这个OCR结果是否对应目标卡
                    is_target_card = False
                    for target_x, target_y, target_image in target_card_positions:
                        distance = ((ocr_center_x - target_x)**2 + (ocr_center_y - target_y)**2) ** 0.5
                        if distance < 100:
                            is_target_card = True
                            break
                    
                    if is_target_card:
                        filtered_results.append(result)
        else:
            # 已经见过目标卡，或者是六星模式：处理所有卡
            filtered_results = [result for result in results if check_card in result.ocr_text]
        
        return filtered_results

    def _select_best_card_from_results(self, filtered_results, min_card_num, ocr_count):
        """
        从过滤后的OCR结果中选择最佳卡片
        :param filtered_results: 过滤后的OCR结果列表
        :param min_card_num: 最低收益阈值
        :param ocr_count: 当前OCR计数
        :return: 选中的RuleClick对象，或None
        """
        logger.info(f"第{ocr_count}次识别到卡: {[result.ocr_text for result in filtered_results]}")
        
        # 提取数字并按数字排序
        numeric_results = []
        for result in filtered_results:
            numbers = [int(num) for num in re.findall(r'\d+', result.ocr_text)]
            if numbers:
                if numbers[0] < min_card_num:
                    logger.debug(f"卡牌收益 {numbers[0]} 低于阈值 {min_card_num}，跳过")
                    continue
                numeric_results.append((numbers[0], result))
        
        if numeric_results:
            # 按数字大到小排序
            sorted_results = [result for _, result in sorted(numeric_results, key=lambda x: x[0], reverse=True)]
            max_result = sorted_results[0]
            
            return self._create_click_target(max_result)
        
        return None

    def _perform_star_special_check(self, target_images, higher_images, min_card_num, check_card, star_mode):
        """
        执行星级模式下的特殊检查
        根据不同的星级模式执行对应的特殊检查逻辑
        
        :param target_images: 目标卡图片列表
        :param higher_images: 干扰卡图片列表
        :param min_card_num: 最低收益阈值
        :param check_card: 卡片类型关键词
        :param star_mode: 星级模式 (CardStar.SIX 或 CardStar.FIVE)
        :return: 选中的RuleClick对象，或None
        """
        if star_mode == CardStar.FIVE:
            # 五星模式
            return self._perform_special_check(target_images, higher_images, min_card_num, check_card, "五星")
        elif star_mode == CardStar.SIX:
            # 六星模式不需要特殊检查，直接返回None
            return None
        else:
            logger.warning(f'不支持的星级模式: {star_mode}，跳过特殊检查')
            return None

    def _perform_special_check(self, target_images, higher_images, min_card_num, check_card, star_mode=None):
        """
        执行特殊检查（当同时检测到目标卡和干扰卡时需要精确匹配）
        
        :param target_images: 目标卡图片列表
        :param higher_images: 干扰卡图片列表
        :param min_card_num: 最低收益阈值
        :param check_card: 卡片类型关键词
        :param star_mode: 可选，星级模式描述，用于日志
        :return: 选中的RuleClick对象，或None
        """
        mode_desc = f"{star_mode}模式" if star_mode else ""
        logger.info(f'执行{mode_desc}特殊检查')
        
        # 1. 获取所有OCR结果
        results = self.O_CHECK_CARD_NUMBER.detect_and_ocr(self.device.image)
        
        # 2. 收集所有卡片位置
        all_cards = self._collect_all_cards_for_special_check(target_images, higher_images)
        if not all_cards:
            logger.warning('特殊检查：未检测到任何卡片')
            return None
        
        # 3. 提取并排序OCR结果
        ocr_list = self._extract_and_sort_ocr_results(results, check_card)
        if not ocr_list:
            logger.warning('特殊检查：未找到有效的OCR结果')
            return None
        
        # 4. 记录检测信息
        self._log_card_ocr_info(all_cards, ocr_list)
        
        # 5. 绑定卡片与OCR结果
        card_ocr_pairs = self._bind_cards_with_ocr(all_cards, ocr_list)
        
        # 6. 筛选满足条件的目标卡
        valid_targets = self._filter_valid_targets(card_ocr_pairs, min_card_num)
        
        # 7. 选择并返回最佳目标卡
        if valid_targets:
            best_target = valid_targets[0]
            logger.info(f'{mode_desc}特殊检查选择挂卡: [{best_target["ocr_text"]}] (目标卡: {best_target["card"].name})')
            return self._create_click_target(best_target['ocr_result'])        
        logger.info(f'{mode_desc}特殊检查未找到满足条件的卡')
        return None

    def _collect_all_cards_for_special_check(self, target_images, higher_images):
        """
        为特殊检查收集所有卡片位置
        使用match_all_any获取去重后的匹配位置
        
        :param target_images: 目标卡图片列表
        :param higher_images: 干扰卡图片列表
        :return: 卡片列表，已按y坐标排序
        """
        all_cards = []
        
        # 收集干扰卡
        for higher_image in higher_images:
            cards = self._collect_cards_by_match_all_any(higher_image, '干扰卡')
            all_cards.extend(cards)
        
        # 收集目标卡
        for target_image in target_images:
            cards = self._collect_cards_by_match_all_any(target_image, '目标卡')
            all_cards.extend(cards)
        
        # 按y坐标排序
        all_cards.sort(key=lambda x: x[3])  # 按center_y排序
        
        return all_cards

    def _collect_cards_by_match_all_any(self, image_obj, card_type_label, threshold=None, nms_threshold=0.3):
        """
        使用match_all_any收集卡片位置
        :param image_obj: RuleImage对象
        :param card_type_label: 卡片类型标签
        :param threshold: 匹配阈值
        :param nms_threshold: 非极大值抑制阈值
        :return: 卡片位置列表
        """
        if threshold is None:
            threshold = image_obj.threshold
        
        cards = []
        matches = image_obj.match_all_any(self.device.image, threshold=threshold, nms_threshold=nms_threshold)
        
        for i, match in enumerate(matches):
            # 解析匹配结果格式 (confidence, x, y, w, h)
            if len(match) == 5:
                confidence, x, y, w, h = match
                center_x = x + w / 2
                center_y = y + h / 2
            elif len(match) == 4:
                x, y, w, h = match
                center_x = x + w / 2
                center_y = y + h / 2
            else:
                continue
            
            cards.append((card_type_label, image_obj, center_x, center_y, threshold))
        
        return cards

    def _extract_and_sort_ocr_results(self, results, check_card):
        """
        提取并排序OCR结果
        :param results: OCR识别结果
        :param check_card: 卡片类型关键词
        :return: 排序后的OCR结果列表
        """
        ocr_list = []
        for result in results:
            if check_card in result.ocr_text:
                # 计算OCR结果的中心位置
                ocr_center_x = result.box[0][0] + (result.box[1][0] - result.box[0][0]) / 2
                ocr_center_y = result.box[0][1] + (result.box[2][1] - result.box[0][1]) / 2
                ocr_center_x += self.O_CHECK_CARD_NUMBER.roi[0]
                ocr_center_y += self.O_CHECK_CARD_NUMBER.roi[1]
                
                # 提取数字
                numbers = [int(num) for num in re.findall(r'\d+', result.ocr_text)]
                if numbers:
                    ocr_list.append({
                        'text': result.ocr_text,
                        'value': numbers[0],
                        'center_x': ocr_center_x,
                        'center_y': ocr_center_y,
                        'result': result
                    })
        
        # 按y坐标排序
        ocr_list.sort(key=lambda x: x['center_y'])
        return ocr_list

    def _log_card_ocr_info(self, all_cards, ocr_list):
        """
        记录卡片和OCR信息
        :param all_cards: 卡片列表
        :param ocr_list: OCR结果列表
        """
        logger.info(f'特殊检查-排序后的卡片: {[(card_type, card_obj.name, center_y) for card_type, card_obj, center_x, center_y, threshold in all_cards]}')
        logger.info(f'特殊检查-排序后的OCR结果: {[ocr["text"] for ocr in ocr_list]}')

    def _bind_cards_with_ocr(self, all_cards, ocr_list):
        """
        绑定卡片与OCR结果
        :param all_cards: 卡片列表
        :param ocr_list: OCR结果列表
        :return: 绑定后的列表
        """
        card_ocr_pairs = []
        
        if len(all_cards) == len(ocr_list):
            # 数量相同，按顺序一对一绑定
            for i, (card_type, card_obj, card_x, card_y, threshold) in enumerate(all_cards):
                if i < len(ocr_list):
                    ocr_info = ocr_list[i]
                    card_ocr_pairs.append({
                        'type': card_type,
                        'card': card_obj,
                        'card_y': card_y,
                        'ocr_text': ocr_info['text'],
                        'ocr_value': ocr_info['value'],
                        'ocr_result': ocr_info['result']
                    })
                    logger.info(f'特殊检查-绑定: {card_type}-{card_obj.name} ↔ {ocr_info["text"]}')
        else:
            # 数量不同，使用最近距离匹配
            logger.warning(f'特殊检查-卡片数量({len(all_cards)})与OCR结果数量({len(ocr_list)})不同，使用距离匹配')
            temp_ocr_list = ocr_list.copy()
            
            for card_type, card_obj, card_x, card_y, threshold in all_cards:
                min_distance = float('inf')
                best_ocr = None
                best_ocr_index = -1
                
                for i, ocr_info in enumerate(temp_ocr_list):
                    distance = ((card_x - ocr_info['center_x'])**2 + (card_y - ocr_info['center_y'])**2) ** 0.5
                    if distance < min_distance and distance < 150:
                        min_distance = distance
                        best_ocr = ocr_info
                        best_ocr_index = i
                
                if best_ocr:
                    card_ocr_pairs.append({
                        'type': card_type,
                        'card': card_obj,
                        'card_y': card_y,
                        'ocr_text': best_ocr['text'],
                        'ocr_value': best_ocr['value'],
                        'ocr_result': best_ocr['result']
                    })
                    logger.info(f'特殊检查-距离绑定: {card_type}-{card_obj.name} ↔ {best_ocr["text"]} 距离: {min_distance:.1f}')
                    # 移除已匹配的OCR结果
                    if best_ocr_index >= 0:
                        temp_ocr_list.pop(best_ocr_index)
        
        return card_ocr_pairs

    def _filter_valid_targets(self, card_ocr_pairs, min_card_num):
        """
        筛选满足条件的目标卡
        :param card_ocr_pairs: 绑定的卡片OCR对列表
        :param min_card_num: 最低收益阈值
        :return: 满足条件的目标卡列表
        """
        valid_targets = []
        for pair in card_ocr_pairs:
            if pair['type'] == '目标卡' and pair['ocr_value'] >= min_card_num:
                valid_targets.append(pair)
                logger.info(f'特殊检查-目标卡 {pair["card"].name} 收益 {pair["ocr_value"]} 满足阈值 {min_card_num}')
        
        # 按收益从高到低排序
        valid_targets.sort(key=lambda x: x['ocr_value'], reverse=True)
        return valid_targets

    def _create_click_target(self, ocr_result):
        """
        创建点击目标
        :param ocr_result: OCR结果对象
        :return: RuleClick对象
        """
        box = ocr_result.box
        x_min = self.O_CHECK_CARD_NUMBER.roi[0] + box[0][0]
        y_min = self.O_CHECK_CARD_NUMBER.roi[1] + box[0][1]
        width = box[1][0] - box[0][0]
        height = box[2][1] - box[1][1]
        roi = int(x_min), int(y_min), int(width), int(height)
        
        return RuleClick(roi_front=roi, roi_back=roi, name="tmpclick")



    def run_activation(self, _config: ActivationConfig) -> bool:
        """
        执行挂卡，要求在结界的界面
        顺便把下一次执行也设置了
        :return: 挂卡成功（）返回True，失败(时间没到提前来了)返回False
        退出的时候还是在挂卡界面而不是结界界面
        """
        self.goto_page(page_guild_card)
        # 太诡异了 为什么有这么长的动画, 那么长的动画先休息一会
        logger.hr('Start activation')
        time.sleep(0.5)
        while 1:
            self.screenshot()
            card_status = self.check_card_status()
            card_effect = self.check_card_effect()

            # 不稳定太，等待动画结束
            if not card_status and not card_effect:
                # 黄色的 ”激活“
                if self.appear(self.I_A_ACTIVATE_YELLOW, threshold=0.95):
                    continue
                if self.appear(self.I_A_DEMOUNT):
                    # 现在在动画里面
                    logger.info('Now in the animation')
                    logger.info('Now there is no card')
                    continue
            # 如果这张卡生效着，在使用中
            if card_status and card_effect:
                logger.info('Card is using')
                interval = self.ocr_time()
                self.set_next_run("KekkaiActivation", target=interval+datetime.now())
                return False
            # 如果已经选中这张卡了， 那就激活这张卡
            if card_status and not card_effect:
                logger.info('Card is selected but not using')
                while 1:
                    self.screenshot()
                    if self.appear(self.I_A_INVITE, threshold=0.8):
                        logger.info('Card is activated')
                        break
                    if self.appear_then_click(self.I_UI_CONFIRM, interval=0.6):
                        continue
                    if self.appear_then_click(self.I_A_ACTIVATE_YELLOW, interval=1):
                        continue
                interval = self.ocr_time(True)
                self.set_next_run("KekkaiActivation", target=interval + datetime.now())
                return True
            # 如果是什么都没有，那就是可以开始挂卡了
            if not card_status and not card_effect:
                logger.info('Card is not selected also not using')
                self.screening_card(_config.card_type)

    def check_card_status(self, screenshot=False) -> bool:
        """
        判断使用有挂卡在上面了， 判断依据就是如果没看就可以显示背景图
        :param screenshot:
        :return: 如果有卡在上面了返回True，否则返回False
        """
        if screenshot:
            self.screenshot()
        return not self.appear(self.I_A_EMPTY)

    def check_card_effect(self, screenshot=False) -> bool:
        """
        检查这张卡是否生效了, 如果是出现的“邀请”那就是生效了， 如果是“激活”那就是还没生效
        :param screenshot:
        :return: 生效返回True
        """
        if screenshot:
            self.screenshot()
        if self.appear(self.I_A_INVITE, threshold=0.8):
            return True
        elif self.appear(self.I_A_ACTIVATE_YELLOW):
            return False
        logger.info('Unknown card effect')
        while 1:
            self.screenshot()
            if self.appear(self.I_A_INVITE, threshold=0.7):
                return True
            elif self.appear(self.I_A_ACTIVATE_YELLOW):
                return False
            elif self.appear(self.I_A_ACTIVATE_GRAY):
                return False

    def ocr_time(self, screenshot=False) -> timedelta or None:
        if screenshot:
            self.screenshot()
        delta = self.O_CARD_ALL_TIME.ocr_duration(self.device.image)
        if not isinstance(delta, timedelta):
            logger.warning('OCR error')
            return None
        if delta == timedelta(0):
            logger.error('The remaining time detected for this card is 0')
            logger.error('This may be due to the fact that the card has not yet been collected')
            raise GameStuckError
        return delta

    def screening_card(self, rule: str):
        """
        开始挑选卡
        :return:
        """

        if rule == CardType.TAIKO:
            card_class = CardClass.TAIKO
            target_class = self.I_A_CARD_KAIKO
        elif rule == CardType.FISH:
            card_class = CardClass.FISH
            target_class = self.I_A_CARD_FISH
        else:
            logger.warning('Unknown card rule')
            self.push_notify(content='Unknown card rule')
            return

        while 1:
            self.screenshot()

            if self.appear(target_class):
                time.sleep(0.3)
                self.screenshot()
                if self.appear(target_class):
                    break
            if self.click(self.C_A_SELECT_CARD_LIST, interval=2.5):
                continue
        logger.info('Appear card class: {}'.format(card_class))
        while 1:
            self.screenshot()
            if not self.appear(target_class):
                break
            if self.appear_then_click(target_class, interval=1):
                continue
        logger.info('Selected card class: {}'.format(card_class))

        # 找最优卡
        while 1:
            self.screenshot()
            target = self.check_card_num()
            if target is None:
                # 未发现卡，处理逻辑
                self._card_not_found()
            if self.appear(self.I_A_EMPTY):
                while 1:
                    self.screenshot()
                    if not self.appear(self.I_A_EMPTY):
                        self.config.kekkai_activation.activation_config.card_not_found_count = 0
                        self.config.save()
                        message = f'✅ 确认挂卡: {rule}'
                        self.save_image(content=message, push_flag=False, wait_time=0)
                        return
                    if self.click(target, interval=1):
                        continue

    def check_card_num(self):
        con = self.config.kekkai_activation.activation_config
        rule = con.card_type
        card_star = con.card_star
        swipe_limit = con.swipe_retry_limit
        
        if rule == CardType.TAIKO:
            min_card_num = con.min_taiko_num
            check_card = "勾玉"
        elif rule == CardType.FISH:
            min_card_num = con.min_fish_num
            check_card = "体力"
        else:
            logger.error('Unknown utilize rule')
            raise ValueError('Unknown utilize rule')
        
        # 获取目标卡和干扰卡图片列表
        star_mapping = self.star_mapping
        target_images = star_mapping['target_images'].get(rule, [])
        higher_images = star_mapping['higher_images'].get(rule, [])
        
        ocr_count = 0
        has_ever_seen_target = False
        special_check_done = False
        
        while True:
            self.screenshot()
            
            # 如果从未见过目标卡，检查当前页面是否有目标卡
            if not has_ever_seen_target:
                has_target = False
                for target_image in target_images:
                    if self.appear(target_image):
                        has_target = True
                        logger.info(f'首次检测到目标卡: {target_image.name}')
                        has_ever_seen_target = True
                        break
                
                # 如果是第一次检测到目标卡且有干扰卡，执行特殊检查
                if has_target and not special_check_done and card_star == CardStar.FIVE:
                    # 检查是否有干扰卡
                    has_higher = False
                    for higher_image in higher_images:
                        if self.appear(higher_image):
                            has_higher = True
                            logger.info(f'检测到干扰卡: {higher_image.name}')
                            break
                    
                    if has_higher:
                        logger.info(f'五星模式下检测到干扰卡，执行特殊检查')
                        special_check_done = True
                        
                        result = self._perform_star_special_check(target_images, higher_images, 
                                                                min_card_num, check_card, card_star)
                        if result:
                            return result
            
            # 常规OCR识别逻辑
            results = self.O_CHECK_CARD_NUMBER.detect_and_ocr(self.device.image)
            ocr_count += 1
            
            # 执行常规OCR检查
            filtered_results = self._perform_regular_ocr_check(results, target_images, higher_images,
                                                            card_star, has_ever_seen_target,
                                                            min_card_num, check_card)
            
            # 从结果中选择最佳卡片
            result = self._select_best_card_from_results(filtered_results, min_card_num, ocr_count)
            if result:
                logger.info(f"选择挂卡: [{result.name}]")
                return result
            
            # 未找到符合条件的卡，检查是否达到滑动上限
            if ocr_count >= swipe_limit:
                logger.warning(f'已达到滑动次数上限({swipe_limit})，未找到符合条件的卡')
                return None
            
            # 执行滑动操作
            logger.info(f"未找到符合条件的卡，准备第{ocr_count+1}次滑动")
            duration = 2
            safe_pos_x = random.randint(200, 400)
            safe_pos_y = random.randint(580, 600)
            p1 = (safe_pos_x, safe_pos_y)
            p2 = (safe_pos_x, safe_pos_y - 410)
            logger.info('Swipe %s -> %s, %sS ' % (point2str(*p1), point2str(*p2), duration))
            self.device.swipe_adb(p1, p2, duration=duration)
            time.sleep(1)
            continue

    def _card_not_found(self):
        # 获取配置引用
        activation_config = self.config.kekkai_activation.activation_config
        # 多少分钟后重试
        retry_minutes = 180
        retry_count = 3
        # 递增未找到卡的计数器
        activation_config.card_not_found_count += 1

        if activation_config.card_not_found_count >= retry_count:
            # 达到重试上限时的处理
            log_msg = f"⚠️{activation_config.card_type}卡未检出（累计{retry_count}次），{retry_minutes}分钟后重试"
            activation_config.card_not_found_count = 0  # 重置计数器并延长下次执行时间
            next_run = datetime.now() + timedelta(minutes=retry_minutes)
        else:
            # # 未达上限切换卡类型
            new_type = (
                CardType.FISH
                if activation_config.card_type == CardType.TAIKO
                else CardType.TAIKO
            )
            log_msg = f"🔄{activation_config.card_type}卡未检出 → 切换{new_type}"
            activation_config.card_type = new_type
            next_run = datetime.now()

        # 统一记录日志和推送
        self.save_image(content=log_msg, push_flag=True)

        # 保存配置并设置下次执行
        self.config.save()
        self.set_next_run("KekkaiActivation", target=next_run)
        raise TaskEnd

    def harvest_card(self):
        """
        收卡的经验
        :return:
        """
        self.appear_then_click(self.I_A_HARVEST_EXP)  # 如果到最后没有领的话有下面的一些图片
        self.appear_then_click(self.I_A_HARVEST_FISH4)  # 斗鱼4/5区别不大 斗鱼的如果一直没有领的话
        self.appear_then_click(self.I_A_HARVEST_KAIKO_4)  # 太鼓4
        self.appear_then_click(self.I_A_HARVEST_KAIKO_3)  # 太鼓3
        self.appear_then_click(self.I_A_HARVEST_KAIKO_6)  # 太鼓6
        self.appear_then_click(self.I_A_HARVEST_FISH_6)  # 斗鱼6
        self.appear_then_click(self.I_A_HARVEST_MOON_3)  # 太阴3
        self.appear_then_click(self.I_A_HARVEST_FISH_3)  # 斗鱼三
