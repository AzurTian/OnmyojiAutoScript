"""Chess runtime: hand, deployment, soul, cleanup, and recall operations."""

# This Python file uses the following encoding: utf-8

import random
import time
from collections import Counter

import cv2
import numpy as np

from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.logger import logger
from tasks.Chess.runtime.board_positions import SET_JADE_AREAS, SET_POSITIONS
from tasks.Chess.runtime.press_and_drag import Press_and_Drag
from tasks.Chess.strategy.shikigami_catalog import SHIKIGAMI_BONDS_BY_ROMAJI


class ChessHandOperationsMixin:
    """Internal mixin; use through ``ScriptTask`` only."""

    def _shikigami_attributes(
        self,
        name: str,
    ) -> tuple[str | None, str | None, str | None]:
        """返回式神本局属性：(守护之印, 御魂1, 御魂2)。"""
        attributes = getattr(self, '_board_shikigami_attributes', {})
        return attributes.get(name, (None, None, None))

    def _set_shikigami_attributes(
        self,
        name: str,
        values: tuple[str | None, str | None, str | None],
    ) -> None:
        attributes = dict(
            getattr(self, '_board_shikigami_attributes', {})
        )
        attributes[name] = values
        self._board_shikigami_attributes = attributes
        logger.debug(f'Chess shikigami attributes: {name}={values}')

    def _shikigami_name_at_set(self, set_index: int) -> str | None:
        """按阵容配置和已确认上阵名单反查指定站位的目标式神。"""
        deployed_names = set(getattr(self, '_board_lineup_names', set()))
        return next((
            name
            for name in deployed_names
            if self.shikigami_deploy_positions.get(name) == set_index
        ), None)

    def _record_shikigami_soul(self, name: str, soul_name: str) -> bool:
        """写入普通御魂槽；重复御魂或两槽已满时拒绝写入。"""
        protect, soul_1, soul_2 = self._shikigami_attributes(name)
        if soul_name in (soul_1, soul_2):
            return False
        if soul_1 is None:
            soul_1 = soul_name
        elif soul_2 is None:
            soul_2 = soul_name
        else:
            return False
        self._set_shikigami_attributes(
            name,
            (protect, soul_1, soul_2),
        )
        return True

    @staticmethod
    def _rule_center(rule: RuleImage | RuleClick) -> tuple[int, int]:
        x, y, width, height = rule.roi_back
        return x + width // 2, y + height // 2

    def _set_position(self, set_index: int) -> tuple[int, int]:
        """读取独立配置中维护的 1-12 号纯站位坐标。"""
        try:
            return tuple(SET_POSITIONS[int(set_index)])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f'Chess board set position is not configured: {set_index}'
            ) from exc

    def _set_jade_area(self, set_index: int) -> tuple[int, int, int, int]:
        """读取独立配置中维护的 1-12 号勾玉占位检测区域。"""
        try:
            return tuple(SET_JADE_AREAS[int(set_index)])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f'Chess board jade area is not configured: {set_index}'
            ) from exc

    def sell_hand_card(self, source: tuple[int, int]) -> None:
        """统一拖到左侧售卖区，避免出售动作改变商店开关状态。"""
        target_rule = self.I_EXPERIENCE
        Press_and_Drag(
            self.device,
            p1=source,
            p2=self._rule_center(target_rule),
            hold_duration=0.5,
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name='CHESS_SELL_UNKNOWN_HAND_CARD',
        )
        self.close_shikigami_specifics_if_open()

    def close_shikigami_specifics_if_open(self) -> bool:
        """卖卡/上卡误打开式神详情页时，点击安全区域直到关闭。"""
        if not hasattr(self, 'I_SHIKIGAMI_SPECIFICS'):
            return False
        if not self.appear(self.I_SHIKIGAMI_SPECIFICS):
            return False

        logger.warning(
            'Chess shikigami specifics opened unexpectedly, close it'
        )
        closed = False
        for attempt in range(1, 8):
            self.click(self.C_CLICK_CLOSE_SPECIFICS_AREA, interval=0.1)
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
            self.screenshot()
            if not self.appear(self.I_SHIKIGAMI_SPECIFICS):
                logger.debug(
                    f'Chess shikigami specifics closed, attempts={attempt}'
                )
                closed = True
                break
        if not closed:
            logger.warning('Chess shikigami specifics still visible')
        return closed

    def sell_rightmost_hand_card(self) -> dict | None:
        """手牌满时直接出售最右侧卡牌，不再识别或保护星级。"""
        hand_cards = self._hand_card_detections()
        if not hand_cards:
            logger.warning(
                'Chess hand is full but no hand-card anchor was detected'
            )
            return None

        target = max(
            hand_cards,
            key=lambda card: card['roi'][0] + card['roi'][2] // 2,
        )
        x, y, width, height = target['roi']
        position = (x + width // 2, y + height // 2)
        identity = self.classify_hand_card(target['roi'])
        sale_key = (identity['type'], identity['name'])
        count_before = self._hand_card_identity_count(*sale_key)
        logger.info(
            f'Sell Chess card: rightmost hand card, '
            f'name={self._shikigami_display_name(identity["name"])}, '
            f'position={position}'
        )
        self.sell_hand_card(position)
        time.sleep(self.HAND_SELL_WAIT)
        self.screenshot()
        self.close_shikigami_specifics_if_open()
        self.screenshot()
        count_after = self._hand_card_identity_count(*sale_key)
        if count_after >= count_before:
            logger.warning(
                'Rightmost Chess card sale not confirmed; '
                f'count={count_before}->{count_after}'
            )
            return None
        logger.info(
            'Rightmost Chess card sale confirmed: '
            f'count={count_before}->{count_after}'
        )
        return {
            'type': 'rightmost',
            'name': identity['name'],
            'position': position,
        }

    def _hakuzosu_protect_target_position(
        self,
        verified_names: set[str] | None = None,
    ) -> int | None:
        """从阵容级配置读取守护之印目标位置。"""
        strategy = self.get_lineup_strategy()
        if self.HAKUZOSU_NAME not in strategy['shikigami']:
            return None
        position = strategy.get('hakuzosu_protect_position')
        if position is not None:
            position = int(position)
            target_name = next((
                name
                for name, config in strategy['shikigami'].items()
                if int(config['position']) == position
            ), None)
            if (
                target_name is not None
                and (
                    verified_names is None
                    or target_name in verified_names
                )
            ):
                return position

        # 兼容尚未迁移的第三方四元组阵容配置。
        for name, config in strategy['shikigami'].items():
            if verified_names is not None and name not in verified_names:
                continue
            if config.get('equip_hakuzosu_protect', False):
                return int(config['position'])
        return None

    def _arakawa_goldfish_target_position(self) -> int | None:
        """返回当前阵容配置的荒川金鱼目标格。"""
        position = self.get_lineup_strategy().get(
            'arakawa_goldfish_position'
        )
        return None if position is None else int(position)

    def _lineup_arakawa_names(self) -> set[str]:
        """返回当前阵容中带有荒川羁绊的式神。"""
        return {
            name
            for name in self.get_lineup_strategy()['shikigami']
            if self.ARAKAWA_BOND_NAME
            in SHIKIGAMI_BONDS_BY_ROMAJI.get(name, ())
        }

    def _predict_arakawa_goldfish_spawn(
        self,
        deploying_set_index: int,
    ) -> int | None:
        """按 12→11→10→9 固定顺序推断金鱼生成位置。"""
        occupied = {
            set_index
            for set_index in self.ARAKAWA_GOLDFISH_SPAWN_POSITIONS
            if self._board_set_has_shikigami(set_index)
        }
        occupied.add(int(deploying_set_index))
        return next((
            set_index
            for set_index in self.ARAKAWA_GOLDFISH_SPAWN_POSITIONS
            if set_index not in occupied
        ), None)

    def _identify_arakawa_goldfish_position(
        self,
        predicted_position: int | None,
    ) -> int | None:
        """严格按 12→11→10→9 逐格打开详情确认金鱼。"""
        candidates = list(self.ARAKAWA_GOLDFISH_SPAWN_POSITIONS)

        for set_index in candidates:
            predicted = set_index == predicted_position
            occupied = self._board_set_has_shikigami(set_index)
            logger.debug(
                'Chess Arakawa goldfish inspect candidate: '
                f'set={set_index}, predicted={predicted}, '
                f'occupied={occupied}'
            )
            # 金鱼刚生成时勾玉图标可能尚未稳定。所有候选位都必须
            # 实际点击确认，occupied 只用于日志诊断，不能用于跳过。
            x, y = self._set_position(set_index)
            inspect_rule = RuleClick(
                roi_front=(x - 8, y - 8, 16, 16),
                roi_back=(x - 8, y - 8, 16, 16),
                name=f'chess_inspect_goldfish_set_{set_index}',
            )
            self.click(inspect_rule, interval=0.1)

            detail_opened = False
            recognized_name = ''
            for _ in range(3):
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
                if not self.appear(self.I_SHIKIGAMI_SPECIFICS):
                    continue
                detail_opened = True
                recognized_name = self._normalize_ocr_text(
                    self.O_SHIKIGAMI_SPECIFICS_NAME.ocr(self.device.image)
                )
                if recognized_name:
                    break

            if detail_opened:
                # 必须严格相等，不能用包含关系，否则“金鱼姬”会误判。
                is_goldfish = recognized_name == '金鱼'
                logger.debug(
                    'Chess board specifics identification: '
                    f'set={set_index}, name={recognized_name or "<empty>"}, '
                    f'is_goldfish={is_goldfish}'
                )
                self.close_shikigami_specifics_if_open()
                self.screenshot()
                if is_goldfish:
                    return set_index

        if predicted_position is not None:
            logger.debug(
                'Chess Arakawa goldfish was not confirmed by exact specifics '
                f'OCR; predicted_set={predicted_position}'
            )
        return None

    def relocate_arakawa_goldfish(
        self,
        predicted_position: int | None,
    ) -> bool:
        """识别荒川金鱼并拖到阵容配置的目标格。"""
        target_position = self._arakawa_goldfish_target_position()
        if target_position is None:
            return False
        source_position = self._identify_arakawa_goldfish_position(
            predicted_position
        )
        if source_position is None:
            logger.warning('Chess Arakawa goldfish position was not found')
            return False
        # 发现后立即登记。若后续拖动或复核失败，本局仍记得它原本所在格。
        self._arakawa_goldfish_current_position = source_position
        protected_before = set(
            getattr(self, '_player_deployed_positions', set())
        )
        if source_position == target_position:
            protected_positions = set(protected_before)
            protected_positions.add(target_position)
            self._player_deployed_positions = protected_positions
            logger.info(
                f'Chess Arakawa goldfish is already at set {target_position}'
            )
            return True
        if not self._ensure_shop_closed():
            return False
        Press_and_Drag(
            self.device,
            p1=self._set_position(source_position),
            p2=self._set_position(target_position),
            hold_duration=0.5,
            point_random=(-2, -2, 2, 2),
            swipe_duration=0.5,
            name=(
                f'CHESS_MOVE_ARAKAWA_GOLDFISH_SET_{source_position}'
                f'_TO_{target_position}'
            ),
        )
        time.sleep(self.BOARD_REDEPLOY_SETTLE_WAIT)
        self.screenshot()
        confirmed_position = self._identify_arakawa_goldfish_position(
            target_position
        )
        if confirmed_position is None:
            logger.warning(
                'Chess Arakawa goldfish move could not be confirmed; '
                f'keep remembered position at set {source_position}'
            )
            protected_before.add(source_position)
            self._player_deployed_positions = protected_before
            return False

        self._arakawa_goldfish_current_position = confirmed_position
        protected_positions = set(protected_before)
        # 金鱼最终所在格必须进入下阵保护。若目标格原本就是脚本上阵的
        # 式神，拖动会发生交换，该式神落到源格后也应继续受保护。
        protected_positions.discard(source_position)
        protected_positions.add(confirmed_position)
        if (
            confirmed_position == target_position
            and target_position in protected_before
        ):
            protected_positions.add(source_position)
        self._player_deployed_positions = protected_positions
        if confirmed_position != target_position:
            logger.warning(
                'Chess Arakawa goldfish did not reach target: '
                f'expected={target_position}, actual={confirmed_position}'
            )
            return False
        logger.info(
            f'Move Chess Arakawa goldfish: '
            f'{source_position} -> {target_position}'
        )
        return True

    def _find_hakuzosu_protect_hand_card(self) -> dict | None:
        """定位手牌中的守护之印。"""
        if self._hakuzosu_protect_target_position() is None:
            return None
        matches = self.hakuzosu_protect_rule.match_all_any(
            self.device.image,
            roi=list(self.HAND_AREA),
            threshold=self.hakuzosu_protect_rule.threshold,
            nms_threshold=0.3,
            frame_id=self.device.image_frame_id,
        )
        if not matches:
            return None
        score, x, y, width, height = max(matches, key=lambda item: item[0])
        return {
            'name': self.HAKUZOSU_PROTECT_NAME,
            'display_name': self.HAKUZOSU_PROTECT_DISPLAY_NAME,
            'score': score,
            'position': (x + width // 2, y + height // 2),
        }

    def _hakuzosu_protect_hand_count(self) -> int:
        """统计完整手牌区中的守护之印数量。"""
        if self._hakuzosu_protect_target_position() is None:
            return 0
        return len(self.hakuzosu_protect_rule.match_all_any(
            self.device.image,
            roi=list(self.HAND_AREA),
            threshold=self.hakuzosu_protect_rule.threshold,
            nms_threshold=0.3,
            frame_id=self.device.image_frame_id,
        ))

    def _hakuzosu_protect_match_in_card(
        self,
        card_roi: tuple[int, int, int, int],
    ) -> dict | None:
        """确认指定手牌框是否为守护之印，用于卖卡保护。"""
        if self._hakuzosu_protect_target_position() is None:
            return None
        matches = self.hakuzosu_protect_rule.match_all_any(
            self.device.image,
            roi=list(card_roi),
            threshold=self.hakuzosu_protect_rule.threshold,
            nms_threshold=0.3,
            frame_id=self.device.image_frame_id,
        )
        if not matches:
            return None
        score, x, y, width, height = max(matches, key=lambda item: item[0])
        return {
            'name': self.HAKUZOSU_PROTECT_NAME,
            'text': self.HAKUZOSU_PROTECT_DISPLAY_NAME,
            'score': score,
            'position': (x + width // 2, y + height // 2),
        }

    def equip_hakuzosu_protect_after_deploy(
        self,
        verified_names: set[str] | None = None,
    ) -> bool:
        """按阵容专属御魂配置尝试装备守护之印。"""
        target_position = self._hakuzosu_protect_target_position(
            verified_names
        )
        if target_position is None:
            return False
        target_name = self._shikigami_name_at_set(target_position)
        if target_name is None:
            return False
        protect, soul_1, soul_2 = self._shikigami_attributes(target_name)
        if protect is not None:
            return False
        if not self._is_preparation_mode():
            return False
        card = self._find_hakuzosu_protect_hand_card()
        if card is None:
            logger.debug(
                'Chess Hakuzosu protect card is not in hand after '
                'Byakuzou deployment'
            )
            return False
        logger.info(
            f'检测到{card["display_name"]}(功能)，'
            f'移动到{target_position}号位'
        )
        protect_before = self._hakuzosu_protect_hand_count()
        if not self._equip_soul_card(
            source=card['position'],
            set_index=int(target_position),
            operation_name=self.HAKUZOSU_PROTECT_NAME.upper(),
        ):
            return False
        time.sleep(self.SOUL_EQUIP_WAIT)
        self.screenshot()
        protect_after = self._hakuzosu_protect_hand_count()
        if protect_after >= protect_before:
            logger.warning(
                'Chess Hakuzosu protect equip not confirmed: '
                f'{target_name} at set {target_position}, '
                f'hand_count={protect_before}->{protect_after}'
            )
            return False
        self._set_shikigami_attributes(
            target_name,
            (self.HAKUZOSU_PROTECT_DISPLAY_NAME, soul_1, soul_2),
        )
        logger.info(
            'Chess Hakuzosu protect equip confirmed: '
            f'{target_name} at set {target_position}'
        )
        return True

    def _equip_soul_card(
        self,
        source: tuple[int, int],
        set_index: int,
        operation_name: str,
    ) -> bool:
        """御魂及阵容特殊手牌共用入口；拖动前必须关闭商店。"""
        if not self._ensure_shop_closed():
            logger.warning(
                f'Abort Chess soul equipment: shop could not be closed, '
                f'operation={operation_name}'
            )
            return False
        target = self._soul_target_position(set_index)
        logger.debug(
            f'Equip Chess soul-type card {operation_name} to set '
            f'{set_index}: source={source}, target={target}'
        )
        Press_and_Drag(
            self.device,
            p1=source,
            p2=target,
            hold_duration=0.5,
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name=f'CHESS_EQUIP_SOUL_{operation_name}_SET_{set_index}',
        )
        return True

    def deploy_shikigami_hand_card(
        self,
        name: str,
        source: tuple[int, int],
    ) -> bool:
        """按当前策略站位拖动式神，并交叉确认是否上阵。"""
        set_index = self.shikigami_deploy_positions.get(name)
        if set_index is None:
            logger.warning(f'Chess shikigami has no deploy position: {name}')
            return False

        if not self._ensure_shop_closed():
            logger.warning(
                f'Abort Chess shikigami deployment: shop is not closed '
                f'before dragging {name}'
            )
            return False
        count_before = self._read_shikigami_count()
        hand_count_before = self._lineup_hand_card_match_count(name)
        target_occupied_before = self._board_set_has_shikigami(set_index)
        target_position = self._set_position(set_index)
        logger.debug(
            f'Deploy Chess shikigami {name} to set {set_index}, '
            f'source={source}, target={target_position}'
        )
        Press_and_Drag(
            self.device,
            p1=source,
            p2=target_position,
            hold_duration=0.5,
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name=f'CHESS_DEPLOY_{name.upper()}_SET_{set_index}',
        )
        self.close_shikigami_specifics_if_open()
        time.sleep(self.HAND_DEPLOY_WAIT)
        self.screenshot()
        count_after = self._read_shikigami_count()
        hand_count_after = self._lineup_hand_card_match_count(name)
        target_occupied_after = self._board_set_has_shikigami(set_index)

        count_increased = False
        if count_before is not None and count_after is not None:
            count_increased = (
                count_after['current'] > count_before['current']
            )
        hand_count_decreased = hand_count_after < hand_count_before
        target_became_occupied = (
            not target_occupied_before and target_occupied_after
        )

        # 与御魂装备采用同一确认逻辑：比较完整手牌区中同名卡数量，
        # 数量减少即确认本次上阵成功。人数和目标格只保留为诊断信息。
        succeeded = hand_count_decreased
        if succeeded:
            logger.debug(
                f'Chess shikigami deploy confirmed: {name} -> set {set_index}, '
                f'board_count={count_before["current"] if count_before else "?"}'
                f'->{count_after["current"] if count_after else "?"}, '
                f'hand_count={hand_count_before}->{hand_count_after}, '
                f'target_occupied={target_occupied_before}'
                f'->{target_occupied_after}'
            )
            return True

        logger.warning(
            f'Chess shikigami deploy not confirmed: {name} -> set {set_index}, '
            f'board_count={count_before["current"] if count_before else "?"}'
            f'->{count_after["current"] if count_after else "?"}, '
            f'hand_count={hand_count_before}->{hand_count_after}, '
            f'target_occupied={target_occupied_before}'
            f'->{target_occupied_after}'
        )
        return False

    def _lineup_hand_card_match_count(self, name: str) -> int:
        """统计手牌区内指定阵容式神的实际卡位数量。"""
        candidates = []
        for rule_name, rule in self.lineup_shikigami_hand_rules:
            if rule_name != name:
                continue
            matches = rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=self.HAND_DEPLOY_TEMPLATE_THRESHOLD,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            )
            candidates.extend(
                (score, x + width // 2, y + height // 2)
                for score, x, y, width, height in matches
            )

        # 同一个式神若存在多个模板，每张实际手牌可能产生多个重叠命中。
        # 以人物中心聚类，只计算一次。
        distinct = []
        for candidate in sorted(candidates, reverse=True):
            _, center_x, center_y = candidate
            if any(
                abs(center_x - kept_x) <= 32
                and abs(center_y - kept_y) <= 40
                for _, kept_x, kept_y in distinct
            ):
                continue
            distinct.append(candidate)
        return len(distinct)

    def _find_best_shikigami_hand_card(
        self,
        excluded_names: set[str] | None = None,
    ) -> dict | None:
        """让阵容头像模板直接扫描整个手牌区，返回最左侧命中卡。"""
        excluded_names = excluded_names or set()
        frame_candidates = []
        for frame_index in range(1, self.HAND_DEPLOY_CONFIRM_FRAMES + 1):
            if frame_index > 1:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
            frame_candidates.append(
                self._scan_lineup_hand_card_candidates_once(excluded_names)
            )

        merged = {}
        for candidates in frame_candidates:
            for candidate in candidates:
                key = (
                    candidate['name'],
                    round(candidate['position'][0] / 12),
                )
                item = merged.setdefault(key, {
                    **candidate,
                    'scores': [],
                    'frames': 0,
                })
                item['scores'].append(candidate['score'])
                item['frames'] += 1

        candidates = []
        for item in merged.values():
            if item['frames'] < self.HAND_DEPLOY_CONFIRM_FRAMES:
                logger.debug(
                    'Skip Chess lineup hand card candidate: '
                    f'name={item["name"]}, frames={item["frames"]}/'
                    f'{self.HAND_DEPLOY_CONFIRM_FRAMES}'
                )
                continue
            avg_score = sum(item['scores']) / len(item['scores'])
            item['score'] = avg_score
            if avg_score < self.HAND_DEPLOY_TEMPLATE_THRESHOLD:
                logger.debug(
                    'Skip Chess lineup hand card candidate below threshold: '
                    f'name={item["name"]}, avg_score={avg_score:.3f}, '
                    f'threshold={self.HAND_DEPLOY_TEMPLATE_THRESHOLD}'
                )
                continue
            candidates.append(item)
            logger.debug(
                'Chess lineup hand card candidate confirmed: '
                f'name={item["name"]}, '
                f'avg_score={avg_score:.3f}, '
                f'position={item["position"]}'
            )

        if not candidates:
            logger.debug('No deployable Chess lineup hand card detected')
            return None

        # 同名多张时先保留最左侧。不同式神先按阵容配置的上阵权重
        # 排序（数值越低越优先），同权重再保持原有的从左到右顺序。
        selected_by_name = {}
        for candidate in sorted(
            candidates,
            key=lambda item: (item['position'][0], -item['score']),
        ):
            selected_by_name.setdefault(candidate['name'], candidate)
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        selected = min(
            selected_by_name.values(),
            key=lambda item: (
                int(
                    strategy_shikigami[item['name']].get(
                        'deploy_weight', 1
                    )
                ),
                item['position'][0],
            ),
        )
        selected['deploy_weight'] = int(
            strategy_shikigami[selected['name']].get('deploy_weight', 1)
        )
        return selected

    def _scan_lineup_hand_card_candidates_once(
        self,
        excluded_names: set[str],
    ) -> list[dict]:
        """单帧：阵容头像模板直接在完整手牌区域内匹配。"""
        candidates = []
        for name, rule in self.lineup_shikigami_hand_rules:
            if name in excluded_names:
                continue
            matches = rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=self.HAND_DEPLOY_TEMPLATE_THRESHOLD,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            )
            for score, x, y, width, height in matches:
                candidate = {
                    'name': name,
                    'score': score,
                    'position': (x + width // 2, y + height // 2),
                }
                logger.info(
                    'Chess deploy hand scan: '
                    f'best={self._shikigami_display_name(name)}, '
                    f'score={score:.3f}, position={candidate["position"]}'
                )
                candidates.append(candidate)

        # 不同角色模板可能在同一张卡上同时得到较低分命中。按人物中心
        # 聚类，每个实际卡位只保留最高分结果，避免同一卡被认成两个人。
        deduplicated = []
        for candidate in sorted(
            candidates,
            key=lambda item: item['score'],
            reverse=True,
        ):
            if any(
                abs(candidate['position'][0] - kept['position'][0]) <= 32
                and abs(candidate['position'][1] - kept['position'][1]) <= 40
                for kept in deduplicated
            ):
                continue
            deduplicated.append(candidate)
        return sorted(
            deduplicated,
            key=lambda item: item['position'][0],
        )

    def _soul_category(self, name: str) -> str | None:
        if name in self.ATTACK_SOUL_NAMES:
            return 'attack'
        if name in self.FUNCTIONAL_SOUL_NAMES:
            return 'functional'
        return None

    def _soul_target_position(self, set_index: int) -> tuple[int, int]:
        """返回御魂类卡牌的投放位置；奇数位统一向北偏移 5 像素。"""
        x, y = self._set_position(set_index)
        if set_index % 2 == 1:
            y += self.SOUL_ODD_SET_Y_OFFSET
        return x, y

    def _soul_targets(
        self,
        soul_name: str,
        category: str,
        verified_names: set[str],
    ) -> list[tuple[int, tuple[int, int]]]:
        """优先返回阵容专属御魂目标，否则按原类型规则选位。"""
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        def can_equip(name: str) -> bool:
            _, soul_1, soul_2 = self._shikigami_attributes(name)
            return (
                soul_name not in (soul_1, soul_2)
                and (soul_1 is None or soul_2 is None)
            )

        preferred_names = {
            name
            for name, config in strategy_shikigami.items()
            if soul_name in config.get('preferred_souls', ())
        }
        active_preferred_names = preferred_names & verified_names
        preferred_positions = sorted(
            int(strategy_shikigami[name]['position'])
            for name in active_preferred_names
            if can_equip(name)
        )
        if preferred_positions:
            return [
                (set_index, self._soul_target_position(set_index))
                for set_index in preferred_positions
            ]

        # 专属目标已经上阵时保持硬优先；若目标式神尚未上阵，则不再
        # 把御魂留在手牌，直接回退到普通攻/功能御魂分配规则。
        if active_preferred_names:
            return []

        active_positions = sorted(
            self.shikigami_deploy_positions[name]
            for name in verified_names
            if name in self.shikigami_deploy_positions
            # 声明过专属御魂的式神是硬约束目标，只能接受其列表中的
            # 御魂；通用输出/功能分类不得再把其他御魂塞给它。
            and not strategy_shikigami[name].get('preferred_souls', ())
        )
        wanted_parity = 0 if category == 'attack' else 1
        targets = []
        for set_index in active_positions:
            target_name = self._shikigami_name_at_set(set_index)
            if (
                set_index % 2 != wanted_parity
                or target_name is None
                or not can_equip(target_name)
            ):
                continue
            # 前排奇数位统一使用向北偏移后的御魂投放位置。
            targets.append((set_index, self._soul_target_position(set_index)))
        return targets

    def _is_lineup_preferred_soul(self, soul_name: str) -> bool:
        """判断御魂是否被当前阵容任一式神列为专属御魂。"""
        return any(
            soul_name in config.get('preferred_souls', ())
            for config in self.get_lineup_strategy()['shikigami'].values()
        )

    def _template_soul_hand_cards(self) -> list[dict]:
        """在手牌区对 soul 模板执行多尺度匹配。"""
        candidates = []
        roi_x, roi_y, roi_width, roi_height = self.HAND_AREA
        source = self.device.image[
            roi_y:roi_y + roi_height,
            roi_x:roi_x + roi_width,
        ]
        for name, rule in self.soul_hand_rules:
            category = self._soul_category(name)
            if category is None:
                continue
            matches = []
            template = rule.image
            for scale in self.SOUL_TEMPLATE_SCALES:
                width = max(1, int(template.shape[1] * scale))
                height = max(1, int(template.shape[0] * scale))
                if width > source.shape[1] or height > source.shape[0]:
                    continue
                scaled = cv2.resize(
                    template,
                    (width, height),
                    interpolation=(
                        cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                    ),
                )
                result = cv2.matchTemplate(
                    source,
                    scaled,
                    cv2.TM_CCOEFF_NORMED,
                )
                locations = np.where(
                    result >= self.SOUL_TEMPLATE_THRESHOLD
                )
                for point_x, point_y in zip(*locations[::-1]):
                    matches.append((
                        float(result[point_y, point_x]),
                        roi_x + int(point_x),
                        roi_y + int(point_y),
                        width,
                        height,
                    ))
            if matches:
                boxes = [list(match[1:]) for match in matches]
                scores = [match[0] for match in matches]
                indices = cv2.dnn.NMSBoxes(
                    boxes,
                    scores,
                    score_threshold=self.SOUL_TEMPLATE_THRESHOLD,
                    nms_threshold=0.3,
                )
                matches = [
                    matches[int(index)]
                    for index in np.array(indices).reshape(-1).tolist()
                ] if len(indices) else []
            for score, x, y, width, height in matches:
                candidates.append({
                    'name': name,
                    'text': self.SOUL_DISPLAY_NAMES[name],
                    'position': (x + width // 2, y + height // 2),
                    'score': score,
                    'source': 'template',
                    'category': category,
                })
                logger.debug(
                    f'Chess soul image matched: {self.SOUL_DISPLAY_NAMES[name]}, '
                    f'score={score:.3f}, box={(x, y, width, height)}'
                )
        return candidates

    def _soul_hand_cards(self) -> list[dict]:
        """仅使用 soul 文件夹图片识别御魂，并按手牌横坐标去重。"""
        merged = []
        candidates = self._template_soul_hand_cards()
        for candidate in sorted(
            candidates,
            key=lambda item: (
                item['position'][0],
                -item['score'],
            ),
        ):
            existing = next((
                item
                for item in merged
                if abs(item['position'][0] - candidate['position'][0]) <= 24
            ), None)
            if existing is None:
                merged.append(candidate)
            elif candidate['score'] > existing['score']:
                merged.remove(existing)
                merged.append(candidate)
        return sorted(merged, key=lambda item: item['position'][0])

    def _soul_match_in_card(
        self,
        card_roi: tuple[int, int, int, int],
        soul_cards: list[dict] | None = None,
    ) -> dict | None:
        """返回落在指定手牌框内的最佳御魂图片匹配。"""
        x, _, width, _ = card_roi
        soul_cards = (
            self._soul_hand_cards() if soul_cards is None else soul_cards
        )
        matches = [
            item
            for item in soul_cards
            if x - 8 <= item['position'][0] <= x + width + 8
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item['score'])

    def _discover_named_hand_cards(
        self,
        expected_text: str,
        allow_fuzzy: bool,
    ) -> list[dict]:
        """使用完整卡名在手牌文字区定位发现类特殊卡。"""
        results = self.O_BADGE_AREA.detect_and_ocr(self.device.image)
        roi_x, roi_y = self.O_BADGE_AREA.roi[:2]
        cards = []
        for result in results:
            text = self._normalize_ocr_text(result.ocr_text).strip(
                '()（）[]【】'
            )
            if not text:
                continue
            if text == expected_text:
                similarity = 1.0
                matched = True
            elif allow_fuzzy:
                matched, similarity, _ = self._fuzzy_text_match(
                    expected_text,
                    text,
                )
            else:
                matched = False
                similarity = 0.0
            if not matched:
                continue

            points = result.box
            left = min(int(point[0]) for point in points)
            right = max(int(point[0]) for point in points)
            top = min(int(point[1]) for point in points)
            bottom = max(int(point[1]) for point in points)
            cards.append({
                'kind': expected_text,
                'text': text,
                'similarity': similarity,
                'score': float(result.score),
                'position': (
                    roi_x + (left + right) // 2,
                    roi_y + (top + bottom) // 2,
                ),
            })
        return sorted(cards, key=lambda item: item['position'][0])

    def _discover_soul_hand_cards(self) -> list[dict]:
        """定位“发现御魂”；保留原有 OCR 编辑距离兜底。"""
        return self._discover_named_hand_cards('发现御魂', allow_fuzzy=True)

    def _discover_badge_hand_cards(self) -> list[dict]:
        """严格按完整四字定位“发现纹章”，禁止仅匹配“纹章”。"""
        return self._discover_named_hand_cards('发现纹章', allow_fuzzy=False)

    def _wait_for_discover_soul_choices(self) -> list[RuleImage]:
        """等待发现御魂三选一界面，并返回本帧实际出现的选项。"""
        deadline = time.monotonic() + self.DISCOVER_SOUL_UI_TIMEOUT
        rules = (
            self.I_SELECT_SOUL_1,
            self.I_SELECT_SOUL_2,
            self.I_SELECT_SOUL_3,
        )
        while time.monotonic() < deadline:
            self.screenshot()
            options = [rule for rule in rules if self.appear(rule)]
            if options:
                return options
            time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
        return []

    def discover_souls_from_hand(self) -> int:
        """优先使用所有“发现御魂/发现纹章”卡并随机选择。"""
        used = 0
        for _ in range(self.DISCOVER_SOUL_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop using Chess discover-soul cards: preparation was '
                    'interrupted or has ended'
                )
                break
            cards = sorted(
                self._discover_badge_hand_cards()
                + self._discover_soul_hand_cards(),
                key=lambda item: item['position'][0],
            )
            if not cards:
                break

            card = cards[0]
            logger.debug(
                f'Use Chess {card["kind"]} hand card: '
                f'text={card["text"]}, '
                f'similarity={card["similarity"]:.3f}, '
                f'position={card["position"]}'
            )
            self.device.click(
                x=card['position'][0],
                y=card['position'][1],
                control_name='CHESS_DISCOVER_CARD',
            )

            use_deadline = time.monotonic() + self.DISCOVER_SOUL_UI_TIMEOUT
            while time.monotonic() < use_deadline:
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
                self.screenshot()
                if not self._is_preparation_mode():
                    logger.debug(
                        'Stop using Chess discover-soul card: preparation was '
                        'interrupted or has ended'
                    )
                    return used
                if self.appear_then_click(self.I_USE_SOUL, interval=0.5):
                    break
            else:
                logger.warning(
                    f'Chess {card["kind"]} card selected, but use button '
                    'did not appear; keep the card and stop this pass'
                )
                break

            options = self._wait_for_discover_soul_choices()
            if not options:
                logger.warning(
                    'Chess discover-soul selection did not appear; '
                    'stop this pass'
                )
                break

            selected = random.choice(options)
            logger.debug(
                f'Random Chess {card["kind"]} option: '
                f'{selected.name}, available={[rule.name for rule in options]}'
            )
            self.click(selected)
            used += 1
            time.sleep(self.DISCOVER_SOUL_WAIT)
            close_deadline = time.monotonic() + self.DISCOVER_SOUL_UI_TIMEOUT
            while time.monotonic() < close_deadline:
                self.screenshot()
                if not any(
                    self.appear(rule)
                    for rule in (
                        self.I_SELECT_SOUL_1,
                        self.I_SELECT_SOUL_2,
                        self.I_SELECT_SOUL_3,
                    )
                ):
                    break
                time.sleep(self.NORMAL_SCREENSHOT_INTERVAL)
            else:
                logger.warning(
                    'Chess discover-soul selection remained open; '
                    'stop this pass'
                )
                break
        else:
            logger.warning(
                'Stop using Chess discover-soul cards at safety limit '
                f'{self.DISCOVER_SOUL_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess discover-soul handling complete, used={used}')
        return used

    def equip_souls_from_hand(
        self,
        verified_names: set[str] | None = None,
    ) -> list[str]:
        """给已确认式神装备御魂，并用完整手牌同名数量减少确认。"""
        if not self._is_preparation_mode():
            logger.debug(
                'Skip equipping Chess souls: preparation was interrupted or '
                'has ended'
            )
            return []
        # “发现御魂”会生成普通御魂，因此必须先全部处理，再扫描并装配
        # soul 文件夹中的御魂卡。
        self.discover_souls_from_hand()
        verified_names = set(verified_names or set())
        if not verified_names:
            logger.debug(
                'Keep Chess souls in hand: no shikigami position was '
                'confirmed on the board'
            )
            return []

        equipped = []
        # 守护之印与普通御魂共享阵容优先目标；它使用独立图片模板，
        # 因此在普通 soul 文件夹扫描前单独处理。每次备阶段都会重试，
        # 不再局限于梦山白藏主刚上阵的瞬间。
        if self.equip_hakuzosu_protect_after_deploy(verified_names):
            equipped.append(self.HAKUZOSU_PROTECT_NAME)
        repeated_attempts = {}
        for _ in range(self.SOUL_EQUIP_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop equipping Chess souls: '
                    'mode is no longer preparation'
                )
                break

            selected = None
            selected_target = None
            soul_candidates = sorted(
                self._soul_hand_cards(),
                key=lambda candidate: (
                    not self._is_lineup_preferred_soul(candidate['name']),
                    candidate['position'][0],
                ),
            )
            for candidate in soul_candidates:
                for target in self._soul_targets(
                    candidate['name'],
                    candidate['category'],
                    verified_names,
                ):
                    attempt_key = (
                        candidate['name'],
                        candidate['position'][0] // 20,
                        target[0],
                    )
                    if repeated_attempts.get(attempt_key, 0) >= 2:
                        continue
                    selected = candidate
                    selected_target = target
                    repeated_attempts[attempt_key] = (
                        repeated_attempts.get(attempt_key, 0) + 1
                    )
                    break
                if selected is not None:
                    break

            if selected is None or selected_target is None:
                break

            set_index, _ = selected_target
            target_name = self._shikigami_name_at_set(set_index)
            if target_name is None:
                break
            hand_counts_before = Counter(
                card['name'] for card in self._soul_hand_cards()
            )
            logger.info(
                f'检测到{selected["text"]}'
                f'({self._soul_category_display(selected["category"])})，'
                f'移动到{set_index}号位'
            )
            if not self._equip_soul_card(
                source=selected['position'],
                set_index=set_index,
                operation_name=selected['name'].upper(),
            ):
                break
            time.sleep(self.SOUL_EQUIP_WAIT)
            self.screenshot()
            hand_counts_after = Counter(
                card['name'] for card in self._soul_hand_cards()
            )
            if (
                hand_counts_after[selected['name']]
                >= hand_counts_before[selected['name']]
            ):
                attempts = repeated_attempts[
                    (
                        selected['name'],
                        selected['position'][0] // 20,
                        set_index,
                    )
                ]
                logger.warning(
                    f'Chess soul equip not confirmed: '
                    f'{selected["text"]} -> set {set_index}, '
                    f'hand_count={hand_counts_before[selected["name"]]}'
                    f'->{hand_counts_after[selected["name"]]}, '
                    f'attempt={attempts}/2'
                )
                continue

            if not self._record_shikigami_soul(
                target_name,
                selected['name'],
            ):
                logger.warning(
                    'Chess soul disappeared from hand but target attributes '
                    f'rejected it: target={target_name}, '
                    f'soul={selected["text"]}'
                )
                continue
            equipped.append(selected['name'])
            logger.debug(
                f'Chess soul equip confirmed: '
                f'{selected["text"]} -> {target_name} at set {set_index}, '
                f'hand_count={hand_counts_before[selected["name"]]}'
                f'->{hand_counts_after[selected["name"]]}'
            )
        else:
            logger.warning(
                'Stop equipping Chess souls at safety limit '
                f'{self.SOUL_EQUIP_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess soul equipment complete, equipped={equipped}')
        return equipped

    def deploy_shikigami_from_hand(self) -> list[str]:
        """关闭商店后上阵手牌式神，并以当前阶数限制场上人数。"""
        # 场上人数 OCR 只有在商店完全收起后才可见。把约束放在上卡
        # 方法内部，避免其他调用入口绕过外层准备流程后无效拖卡。
        if not self._is_preparation_mode():
            logger.debug(
                'Skip Chess shikigami deployment: preparation was interrupted '
                'or has ended'
            )
            return []
        if not self._ensure_shop_closed():
            logger.warning(
                'Skip Chess shikigami deployment: shop could not be closed'
            )
            return []
        if self._is_shop_open():
            logger.warning(
                'Skip Chess shikigami deployment: shop is still visible '
                'after close confirmation'
            )
            return []

        deployed = []
        deployed_names = set(getattr(self, '_board_lineup_names', set()))
        player_positions = set(
            getattr(self, '_player_deployed_positions', set())
        )

        # 已确认上阵的阵容式神在本局内保持登记。战斗动画、遮挡或勾玉
        # 模板单帧漏识别不能证明式神已经离场；若据此清除名称，会同时
        # 导致重复上阵和专属御魂失去目标。
        failed_attempts = {}
        for _ in range(self.HAND_DEPLOY_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop deploying Chess hand cards: '
                    'mode is no longer preparation'
                )
                break
            if not self._ensure_shop_closed():
                logger.warning(
                    'Stop deploying Chess hand cards: shop reopened or '
                    'could not be confirmed closed before capacity check'
                )
                break

            capacity = self._read_lineup_capacity_status()
            if capacity is None:
                logger.warning(
                    'Stop deploying Chess hand cards: lineup capacity '
                    'could not be confirmed'
                )
                break
            lineup_full = capacity['full']
            candidate = self._find_best_shikigami_hand_card(
                excluded_names=(
                    deployed_names
                    | {
                        name
                        for name, attempts in failed_attempts.items()
                        if attempts >= 2
                    }
                ),
            )
            if candidate is None:
                logger.info(
                    'Stop deploying Chess hand cards: no deployable lineup '
                    'hand card candidate'
                )
                break

            logger.info(
                f'Chess deploy candidate: '
                f'{self._shikigami_display_name(candidate["name"])}, '
                f'weight={candidate.get("deploy_weight", 1)}, '
                f'score={candidate["score"]:.3f}, '
                f'position={candidate["position"]}'
            )
            set_index = self.shikigami_deploy_positions[candidate['name']]
            if lineup_full:
                recalled_set = self._recall_one_system_board_card(
                    preferred_set_index=set_index,
                )
                if recalled_set is None:
                    logger.warning(
                        'Stop deploying Chess hand cards: lineup is full and '
                        'no removable system-deployed card was found at '
                        f'{self.BOARD_RECALL_POSITIONS}'
                    )
                    break
                capacity = self._read_lineup_capacity_status()
                if capacity is None or capacity['full']:
                    logger.warning(
                        'Stop deploying Chess hand cards: system card recall '
                        f'at set {recalled_set} did not free lineup capacity'
                    )
                    break

                # 下阵卡进入手牌后会让整排手牌重新布局。下阵前保存的
                # candidate.position 已失效，必须基于新截图重新定位同名卡。
                self.screenshot()
                candidate_name = candidate['name']
                candidate = self._find_best_shikigami_hand_card(
                    excluded_names=(
                        set(self.shikigami_deploy_positions)
                        - {candidate_name}
                    ),
                )
                if candidate is None or candidate['name'] != candidate_name:
                    logger.warning(
                        'Stop current Chess deployment after system recall: '
                        f'{self._shikigami_display_name(candidate_name)} '
                        'could not be relocated in the reflowed hand'
                    )
                    failed_attempts[candidate_name] = (
                        failed_attempts.get(candidate_name, 0) + 1
                    )
                    continue
                set_index = self.shikigami_deploy_positions[candidate_name]
                logger.info(
                    f'Recall Chess system card at set {recalled_set}, then '
                    f'deploy {self._shikigami_display_name(candidate["name"])} '
                    f'to set {set_index}, refreshed_position='
                    f'{candidate["position"]}'
                )

            arakawa_names = self._lineup_arakawa_names()
            should_locate_goldfish = (
                self._arakawa_goldfish_target_position() is not None
                and getattr(
                    self,
                    '_arakawa_goldfish_current_position',
                    None,
                ) is None
                and candidate['name'] in arakawa_names
                and bool(deployed_names & arakawa_names)
            )
            predicted_goldfish_position = (
                self._predict_arakawa_goldfish_spawn(set_index)
                if should_locate_goldfish
                else None
            )

            if not self.deploy_shikigami_hand_card(
                candidate['name'],
                candidate['position'],
            ):
                failed_attempts[candidate['name']] = (
                    failed_attempts.get(candidate['name'], 0) + 1
                )
                logger.warning(
                    f'Retry Chess shikigami deployment later: '
                    f'{candidate["name"]}, '
                    f'attempt={failed_attempts[candidate["name"]]}/2'
                )
                continue

            deployed.append(candidate['name'])
            deployed_names.add(candidate['name'])
            self._board_lineup_names = deployed_names
            if candidate['name'] not in getattr(
                self,
                '_board_shikigami_attributes',
                {},
            ):
                self._set_shikigami_attributes(
                    candidate['name'],
                    (None, None, None),
                )
            player_positions = set(
                getattr(self, '_player_deployed_positions', set())
            )
            player_positions.add(set_index)
            self._player_deployed_positions = player_positions
            logger.debug(
                'Mark Chess player-deployed position: '
                f'set={set_index}, name={candidate["name"]}'
            )
            if should_locate_goldfish:
                self.relocate_arakawa_goldfish(
                    predicted_goldfish_position
                )
            if candidate['name'] == self.HAKUZOSU_NAME:
                self.equip_hakuzosu_protect_after_deploy(deployed_names)
        else:
            logger.warning(
                'Stop deploying Chess hand cards at safety limit '
                f'{self.HAND_DEPLOY_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess hand deployment complete, deployed={deployed}')
        return deployed

    def _hand_card_detections(self) -> list[dict]:
        """直接用式神/御魂素材定位已收录手牌，不依赖羁绊 OCR。"""
        template_rules = [
            rule
            for _, rule in (
                list(self.shikigami_hand_rules)
                + list(self.soul_hand_rules)
            )
        ]
        template_rules.append(self.hakuzosu_protect_rule)
        candidates = []
        for rule in template_rules:
            matches = rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=rule.threshold,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            )
            for score, x, y, width, height in matches:
                candidates.append((score, x, y, width, height))

        # 多个素材可能在同一张卡上产生近邻命中；每个实际卡位只保留
        # 最高分结果。这里保留素材自身矩形，拖动时使用其中心即可。
        card_matches = []
        for candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
            _, x, y, width, height = candidate
            center_x = x + width // 2
            center_y = y + height // 2
            if any(
                abs(center_x - (kept[1] + kept[3] // 2)) <= 28
                and abs(center_y - (kept[2] + kept[4] // 2)) <= 40
                for kept in card_matches
            ):
                continue
            card_matches.append(candidate)

        detections = []
        for score, x, y, width, height in sorted(
            card_matches,
            key=lambda item: item[1],
        ):
            if width <= 0 or height <= 0:
                continue
            detection = {
                'roi': (x, y, width, height),
                'score': score,
            }
            detections.append(detection)
            logger.debug(
                f'Chess hand card template detected: score={score:.3f}, '
                f'roi={detection["roi"]}'
            )
        if not detections:
            logger.debug('Chess hand card templates found no cards')
        return detections

    def _hand_card_rois(self) -> list[tuple[int, int, int, int]]:
        """兼容只需要卡框的分类流程。"""
        return [item['roi'] for item in self._hand_card_detections()]

    def _hand_card_identity_count(
        self,
        card_type: str,
        name: str | None,
    ) -> int:
        """统计手牌中指定素材的命中张数，用于确认出售确实生效。"""
        if card_type == 'shikigami' and name:
            rules = [
                rule
                for rule_name, rule in self.shikigami_hand_rules
                if rule_name == name
            ]
        elif card_type == 'soul' and name:
            rules = [
                rule
                for rule_name, rule in self.soul_hand_rules
                if rule_name == name
            ]
        else:
            return len(self._hand_card_detections())

        matches = []
        for rule in rules:
            matches.extend(rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=rule.threshold,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            ))

        centers = []
        for score, x, y, width, height in sorted(
            matches,
            key=lambda item: item[0],
            reverse=True,
        ):
            center = (x + width // 2, y + height // 2)
            if any(
                abs(center[0] - kept[0]) <= 28
                and abs(center[1] - kept[1]) <= 40
                for kept in centers
            ):
                continue
            centers.append(center)
        return len(centers)

    def cleanup_non_lineup_hand_cards(
        self,
        allowed_modes: tuple[str, ...] = ('战',),
        emergency: bool = False,
    ) -> list[tuple[int, int]]:
        """独立卖卡环节：循环出售纹章和非阵容卡，直到连续确认干净。"""
        if not emergency and self._is_early_round_layout():
            logger.debug(
                'Skip Chess hand cleanup: '
                'alternate layout means round 1-3'
            )
            return []

        sold = []
        failed_sale_attempts = {}
        clean_confirm_frames = 0
        strategy = self.get_lineup_strategy()
        logger.debug(
            'Chess hand cleanup lineup protection: '
            f'lineup={strategy["key"]}, '
            f'names={list(strategy["shikigami"].keys())}'
        )
        for cleanup_pass in range(1, self.HAND_CLEANUP_SAFETY_LIMIT + 1):
            self.close_shikigami_specifics_if_open()
            mode = self._read_chess_mode()
            if not self._is_hand_cleanup_allowed(allowed_modes):
                logger.debug(
                    'Stop cleaning Chess hand cards: '
                    f'mode={mode} is outside {allowed_modes}'
                )
                break

            # 纹章没有式神卡左上角的星级标志，无法进入下面的卡框分类。
            # 直接在 badge_area 中定位“纹章”文本，并从文字所在卡片拖出出售。
            badge_target = self._find_badge_hand_card()
            if badge_target is not None:
                logger.info(
                    'Sell Chess card: '
                    f'text={badge_target["text"]}, '
                    f'position={badge_target["position"]}'
                )
                self.sell_hand_card(badge_target['position'])
                sold.append(badge_target['position'])
                clean_confirm_frames = 0
                time.sleep(self.HAND_CLEANUP_REFLOW_WAIT)
                self.screenshot()
                continue

            # 御魂图片可能与星级卡框同时命中。先独立识别御魂，避免
            # classify_hand_card 的固定尺寸模板漏检后将它当作 unknown 出售。
            soul_cards = self._soul_hand_cards()
            discover_cards = (
                self._discover_soul_hand_cards()
                + self._discover_badge_hand_cards()
            )
            sell_target = None
            for card_roi in self._hand_card_rois():
                card_x, _, card_width, _ = card_roi
                discover_card = next((
                    item
                    for item in discover_cards
                    if (
                        card_x - 8
                        <= item['position'][0]
                        <= card_x + card_width + 8
                    )
                ), None)
                if discover_card is not None:
                    logger.debug(
                        'Keep unused Chess discover card during cleanup: '
                        f'text={discover_card["text"]}, '
                        f'position={discover_card["position"]}'
                    )
                    continue
                soul = self._soul_match_in_card(card_roi, soul_cards)
                if soul is not None:
                    logger.debug(
                        'Keep Chess soul hand card during cleanup: '
                        f'name={soul["text"]}, score={soul["score"]:.3f}, '
                        f'position={soul["position"]}'
                    )
                    continue
                protect = self._hakuzosu_protect_match_in_card(card_roi)
                if protect is not None:
                    logger.debug(
                        'Keep Chess Hakuzosu protect card during cleanup: '
                        f'score={protect["score"]:.3f}, '
                        f'position={protect["position"]}'
                    )
                    continue
                result = self.classify_hand_card(card_roi)
                keep = (
                    result['type'] == 'soul'
                    or (
                        result['type'] == 'shikigami'
                        and result['name'] in self.shikigami_deploy_positions
                    )
                )
                if keep:
                    continue

                if result['type'] == 'unknown':
                    # 低阈值阵容保护只用于无法分类的卡。已经被完整素材库
                    # 明确识别为非阵容式神的卡不能再被 0.58 的模糊匹配
                    # 覆盖，否则会出现日志列出杂卡但卖卡阶段始终保留。
                    possible = self._possible_lineup_shikigami(card_roi)
                    if possible is not None:
                        logger.debug(
                            'Protect possible lineup Chess hand card from sale: '
                            f'name={possible["name"]}, '
                            f'score={possible["score"]:.3f}'
                        )
                        continue
                    result = self._confirm_unknown_hand_card(card_roi)
                    if result is None:
                        continue
                sale_key = (result['type'], result['name'])
                if failed_sale_attempts.get(sale_key, 0) >= 2:
                    logger.debug(
                        'Skip repeatedly failed Chess sale target in this '
                        f'cleanup pass: type={result["type"]}, '
                        f'name={result["name"]}'
                    )
                    continue
                sell_target = result
                break
            if sell_target is None:
                clean_confirm_frames += 1
                if (
                    clean_confirm_frames
                    >= self.HAND_CLEANUP_CLEAN_CONFIRM_FRAMES
                ):
                    logger.debug(
                        'Chess hand cleanup confirmed clean: '
                        f'frames={clean_confirm_frames}'
                    )
                    break
                logger.debug(
                    'No sellable Chess hand card in current scan, '
                    'wait for layout and verify again: '
                    f'frame={clean_confirm_frames}/'
                    f'{self.HAND_CLEANUP_CLEAN_CONFIRM_FRAMES}'
                )
                time.sleep(self.HAND_CLEANUP_REFLOW_WAIT)
                self.screenshot()
                continue

            logger.info(
                f'Sell Chess card: '
                f'type={sell_target["type"]}, '
                f'name={self._shikigami_display_name(sell_target["name"])}, '
                f'position={sell_target["position"]}'
            )
            sale_key = (sell_target['type'], sell_target['name'])
            count_before = self._hand_card_identity_count(*sale_key)
            self.sell_hand_card(sell_target['position'])
            time.sleep(self.HAND_CLEANUP_REFLOW_WAIT)
            self.screenshot()
            self.close_shikigami_specifics_if_open()
            self.screenshot()
            count_after = self._hand_card_identity_count(*sale_key)
            if count_after < count_before:
                sold.append(sell_target['position'])
                failed_sale_attempts.pop(sale_key, None)
                clean_confirm_frames = 0
                logger.info(
                    'Chess card sale confirmed: '
                    f'type={sell_target["type"]}, '
                    f'name={self._shikigami_display_name(sell_target["name"])}, '
                    f'count={count_before}->{count_after}'
                )
                continue

            failed_sale_attempts[sale_key] = (
                failed_sale_attempts.get(sale_key, 0) + 1
            )
            clean_confirm_frames = 0
            logger.warning(
                'Chess card sale not confirmed; do not register as sold: '
                f'type={sell_target["type"]}, '
                f'name={self._shikigami_display_name(sell_target["name"])}, '
                f'count={count_before}->{count_after}, '
                f'attempt={failed_sale_attempts[sale_key]}/2'
            )
        else:
            logger.warning(
                'Stop cleaning Chess hand cards at safety limit '
                f'{self.HAND_CLEANUP_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess non-lineup hand cleanup complete, sold={sold}')
        return sold

    def _is_hand_cleanup_allowed(
        self,
        allowed_modes: tuple[str, ...] = ('战',),
    ) -> bool:
        """卖卡只在调用方指定阶段执行，阶段变化后立刻停止。"""
        return self._read_chess_mode() in allowed_modes

    def _free_one_hand_slot_for_purchase(
        self,
        handle_souls_first: bool = True,
    ) -> dict | None:
        """购买受阻时先处理御魂；重试仍失败才出售最右侧卡牌。"""

        mode = self._read_chess_mode()
        if mode not in ('备', '战'):
            logger.warning(
                f'Cannot run emergency Chess hand cleanup in mode={mode}'
            )
            return None

        # 手牌只能在商店关闭后完整显示。第一次购买未生效时，先检查并
        # 装备御魂，再恢复商店让调用方重新尝试购买；只有重试后仍未
        # 购入，调用方才会以 handle_souls_first=False 进入卖卡兜底。
        if handle_souls_first and mode == '备':
            if not self._ensure_shop_closed():
                logger.warning(
                    'Cannot inspect Chess hand souls: shop could not be closed'
                )
                return None
            self.screenshot()
            soul_cards = self._soul_hand_cards()
            if soul_cards:
                verified_board_names = {
                    name
                    for name in getattr(self, '_board_lineup_names', set())
                    if name in self.shikigami_deploy_positions
                }
                logger.info(
                    'Chess purchase recovery found souls in hand; '
                    'equip them before retrying purchase'
                )
                equipped = self.equip_souls_from_hand(verified_board_names)
                if not self._ensure_shop_open():
                    logger.warning(
                        'Chess soul recovery completed, but shop could not '
                        'be reopened'
                    )
                    return None
                self.screenshot()
                return {
                    'type': 'souls',
                    'equipped': equipped,
                }

        result = self.sell_rightmost_hand_card()

        if result is None:
            logger.warning('No safe Chess hand card is available to free a slot')
            return None

        # 本方法只会在购买失败的恢复路径调用；清理后必须恢复“商店开”
        # 这一购买前置状态，至于卖卡过程本身不主动切换商店。
        if not self._ensure_shop_open():
            logger.warning(
                'Emergency Chess hand cleanup succeeded, but shop could not '
                'be reopened'
            )
            return None
        self.screenshot()
        return result

    def _find_badge_hand_card(self) -> dict | None:
        """返回 badge_area 内最左侧“纹章”文字的屏幕坐标。"""
        results = self.O_BADGE_AREA.detect_and_ocr(self.device.image)
        matches = []
        roi_x, roi_y = self.O_BADGE_AREA.roi[:2]
        for result in results:
            text = self._normalize_ocr_text(result.ocr_text).strip(
                '()（）[]【】'
            )
            # “发现纹章”必须由专用完整卡名流程处理；若这里只按
            # “纹章”子串判断，会在使用前被当作普通纹章卖掉并卡死。
            if text == '发现纹章':
                continue
            if '纹章' not in text:
                continue

            # detect_and_ocr 返回的是相对于 OCR 裁剪区的四点框。
            points = result.box
            left = min(int(point[0]) for point in points)
            right = max(int(point[0]) for point in points)
            top = min(int(point[1]) for point in points)
            bottom = max(int(point[1]) for point in points)
            position = (
                roi_x + (left + right) // 2,
                roi_y + (top + bottom) // 2,
            )
            matches.append({
                'text': text,
                'position': position,
                'score': float(result.score),
            })

        if not matches:
            return None
        matches.sort(key=lambda item: item['position'][0])
        return matches[0]

    def _recall_one_system_board_card(
        self,
        preferred_set_index: int | None = None,
    ) -> int | None:
        """满员上卡时只下阵一个系统卡位，成功则返回对应站位。"""
        if not self._is_preparation_mode():
            return None
        if not self._ensure_shop_closed():
            logger.warning(
                'Cannot free Chess lineup slot: shop could not be closed'
            )
            return None

        player_positions = set(
            getattr(self, '_player_deployed_positions', set())
        )
        positions = list(self.BOARD_RECALL_POSITIONS)
        if preferred_set_index in positions:
            positions.remove(preferred_set_index)
            positions.insert(0, preferred_set_index)

        hand_target = self._rule_center(
            RuleClick(
                roi_front=self.HAND_AREA,
                roi_back=self.HAND_AREA,
                name='chess_hand_area',
            )
        )
        time.sleep(self.BOARD_RECALL_SETTLE_WAIT)
        for set_index in positions:
            if set_index in player_positions:
                continue
            if not self._board_set_has_shikigami(set_index):
                continue

            source = self._set_position(set_index)
            for attempt, drag_source in enumerate(
                (source, (source[0], source[1] - 14)),
                start=1,
            ):
                Press_and_Drag(
                    self.device,
                    p1=drag_source,
                    p2=hand_target,
                    hold_duration=0.6 if attempt == 2 else 0.5,
                    point_random=(-2, -2, 2, 2),
                    swipe_duration=0.5,
                    name=(
                        f'CHESS_FREE_SYSTEM_SET_{set_index}'
                        f'_ATTEMPT_{attempt}'
                    ),
                )
                time.sleep(self.BOARD_RECALL_SETTLE_WAIT)
                self.screenshot()
                if not self._board_set_has_shikigami(set_index):
                    tracked_names = set(
                        getattr(self, '_board_lineup_names', set())
                    )
                    self._board_lineup_names = {
                        name
                        for name in tracked_names
                        if self.shikigami_deploy_positions.get(name)
                        != set_index
                    }
                    logger.debug(
                        f'Chess system card recalled for deployment: '
                        f'set={set_index}, attempt={attempt}'
                    )
                    return set_index
        return None

    def recall_all_board_cards(self) -> bool:
        """按系统自动上阵顺序，快速回收棋盘右侧四个候选位置。"""
        if not self._ensure_shop_closed():
            logger.warning(
                'Abort Chess board recall: shop could not be closed'
            )
            return False
        hand_target = self._rule_center(
            RuleClick(
                roi_front=self.HAND_AREA,
                roi_back=self.HAND_AREA,
                name='chess_hand_area',
            )
        )

        count = self._read_shikigami_count()
        if count is not None and count['current'] == 0:
            logger.debug('Chess board is already empty; skip recall')
            self._board_lineup_names = set()
            self._player_deployed_positions = set()
            return True

        tracked_names = set(getattr(self, '_board_lineup_names', set()))
        player_positions = set(
            getattr(self, '_player_deployed_positions', set())
        )
        recall_positions = tuple(
            set_index
            for set_index in self.BOARD_RECALL_POSITIONS
            if set_index not in player_positions
        )
        protected_recall_positions = sorted(
            set(self.BOARD_RECALL_POSITIONS) & player_positions
        )
        if protected_recall_positions:
            logger.debug(
                'Keep Chess system-set positions during recall: '
                f'they were deployed by script, positions='
                f'{protected_recall_positions}'
            )
        logger.debug(
            f'Chess board recall order: {recall_positions}, '
            f'current_count={None if count is None else count["current"]}'
        )
        if not self._is_preparation_mode():
            logger.debug(
                'Stop recalling Chess board cards: '
                'mode is no longer preparation'
            )
            return False

        # 商店图层消失后，棋盘的触控层仍有一小段收起动画。日志显示此前
        # 11 号位在关闭判定后立即拖动，手势已下发但没有成功下阵。
        time.sleep(self.BOARD_RECALL_SETTLE_WAIT)

        # 除 11 号位的针对性确认外，其余候选格连续拖完后再统一截图，
        # 避免每个空位都产生一次截图等待。
        for set_index in recall_positions:
            if not self._board_set_has_shikigami(set_index):
                logger.debug(
                    f'Skip Chess recall set {set_index}: '
                    'jade marker is not detected'
                )
                continue
            source = self._set_position(set_index)
            Press_and_Drag(
                self.device,
                p1=source,
                p2=hand_target,
                hold_duration=0.5,
                point_random=(-3, -3, 3, 3),
                swipe_duration=0.45,
                name=f'CHESS_RECALL_SET_{set_index}',
            )
            time.sleep(self.BOARD_RECALL_INTERVAL)

            # 11 号位是系统自动上阵的第一顺位，也是商店关闭后的第一条
            # 棋盘手势。单独确认它是否生效；失败时稍微上移到模型主体重拖。
            if set_index == 11 and count is not None:
                self.screenshot()
                set_11_count = self._read_shikigami_count()
                if (
                    set_11_count is not None
                    and set_11_count['current'] >= count['current']
                ):
                    retry_source = (source[0], source[1] - 14)
                    logger.warning(
                        'Chess set 11 recall did not reduce lineup count; '
                        f'retry from {retry_source}'
                    )
                    time.sleep(self.BOARD_RECALL_RETRY_WAIT)
                    Press_and_Drag(
                        self.device,
                        p1=retry_source,
                        p2=hand_target,
                        hold_duration=0.6,
                        point_random=(-2, -2, 2, 2),
                        swipe_duration=0.5,
                        name='CHESS_RECALL_SET_11_RETRY',
                    )
                    time.sleep(self.BOARD_RECALL_INTERVAL)
                    self.screenshot()
                    set_11_count = self._read_shikigami_count()
                    logger.debug(
                        'Chess set 11 recall retry result: '
                        f'{None if set_11_count is None else set_11_count["current"]}'
                        f'/{None if set_11_count is None else set_11_count["total"]}'
                    )
                if set_11_count is not None:
                    count = set_11_count

        self.screenshot()
        count = self._read_shikigami_count()
        # 只清除脚本记录中确实位于本次回收区域的式神。若 9 号位是脚本
        # 上阵的卡，或场上仍有 1-8 号位的式神，则保留对应记录。
        self._board_lineup_names = {
            name
            for name in tracked_names
            if self.shikigami_deploy_positions.get(name)
            not in recall_positions
        }
        self._player_deployed_positions = (
            player_positions - set(recall_positions)
        )
        if count is not None and count['current'] == 0:
            self._board_lineup_names = set()
            self._player_deployed_positions = set()
        if count is None:
            logger.debug('Chess board recall completed; count is unavailable')
        else:
            logger.debug(
                'Chess board recall completed at positions '
                f'{self.BOARD_RECALL_POSITIONS}: '
                f'{count["current"]}/{count["total"]}'
            )
        return True
