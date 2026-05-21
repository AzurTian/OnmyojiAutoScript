# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import cv2
import numpy as np

from numpy import float32, int32, uint8, fromfile
from pathlib import Path

from module.base.decorator import cached_property
from module.image.rpc import get_image_client
from module.logger import logger
from module.base.utils import is_approx_rectangle


class RuleImage:
    debug_mode: bool = False
    METHOD_TEMPLATE_MATCH = "Template matching"
    METHOD_MULTI_SCALE_TEMPLATE_MATCH = "Multi-scale template matching"
    METHOD_SIFT_FLANN = "Sift Flann"
    DEFAULT_MULTI_SCALE_RANGE = (0.6, 1.2)
    DEFAULT_MULTI_SCALE_STEP = 0.1

    def __init__(self, roi_front: tuple, roi_back: tuple, method: str, threshold: float, file: str) -> None:
        """
        初始化
        :param roi_front: 前置roi
        :param roi_back: 后置roi 用于匹配的区域
        :param method: 匹配方法 "Template matching" / "Multi-scale template matching" / "Sift Flann"
        :param threshold: 阈值  0.8
        :param file: 相对路径, 带后缀
        """
        self._match_init = False  # 这个是给后面的 等待图片稳定
        self._image = None  # 这个是匹配的目标
        self._kp = None  #
        self._des = None
        self.method = method

        self.roi_front: list = list(roi_front)
        self.roi_back = roi_back
        self.threshold = threshold
        self.file = file
        self.scale_range: tuple[float, float] | tuple[float, float, float] | None = None
        self.scale_step: float = self.DEFAULT_MULTI_SCALE_STEP

    @cached_property
    def name(self) -> str:
        """

        :return:
        """
        return Path(self.file).stem.upper()

    def __str__(self):
        return self.name

    __repr__ = __str__

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self.name)

    def __bool__(self):
        return True

    def load_image(self) -> None:
        """
        加载图片
        :return:
        """
        if self._image is not None:
            return
        img = cv2.imdecode(fromfile(self.file, dtype=uint8), -1)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self._image = img

        height, width, channels = self._image.shape
        if height != self.roi_front[3] or width != self.roi_front[2]:
            self.roi_front[2] = width
            self.roi_front[3] = height
            logger.debug(f"{self.name} roi_front size changed to {width}x{height}")

    def load_kp_des(self) -> None:
        if self._kp is not None and self._des is not None:
            return
        self._kp, self._des = self.sift.detectAndCompute(self.image, None)

    @property
    def image(self):
        """
        获取图片
        :return:
        """
        if self._image is None:
            self.load_image()
        return self._image

    @property
    def is_template_match(self) -> bool:
        """
        是否是模板匹配
        :return:
        """
        return self.method == self.METHOD_TEMPLATE_MATCH

    @property
    def is_multi_scale_template_match(self) -> bool:
        return self.method == self.METHOD_MULTI_SCALE_TEMPLATE_MATCH

    @property
    def is_sift_flann(self) -> bool:
        return self.method == self.METHOD_SIFT_FLANN

    @cached_property
    def sift(self):
        return cv2.SIFT_create()

    @cached_property
    def kp(self):
        if self._kp is None:
            self.load_kp_des()
        return self._kp

    @cached_property
    def des(self):
        if self._des is None:
            self.load_kp_des()
        return self._des

    def corp(self, image: np.array, roi: list = None) -> np.array:
        """
        截取图片
        :param image:
        :param roi
        :return:
        """
        if roi is None:
            x, y, w, h = self.roi_back
        else:
            x, y, w, h = roi
        x, y, w, h = int(x), int(y), int(w), int(h)
        return image[y:y + h, x:x + w]

    def _template_image_invalid(self, mat: np.array) -> bool:
        if mat is None or mat.shape[0] == 0 or mat.shape[1] == 0:
            mat_shape = None if mat is None else mat.shape
            logger.error(f"Template image is invalid: {mat_shape}")  # 检测模板尺寸，避免非法模板参与匹配
            return True
        return False

    def _update_roi_front(self, loc: tuple[int, int], size: tuple[int, int]) -> None:
        self.roi_front[0] = loc[0] + self.roi_back[0]
        self.roi_front[1] = loc[1] + self.roi_back[1]
        self.roi_front[2] = size[0]
        self.roi_front[3] = size[1]

    def to_service_payload(self) -> dict:
        file_path = ""
        if self.file:
            file_path = str(Path(self.file).resolve())
        scale_range = None
        if self.scale_range is not None:
            scale_range = list(self.scale_range)
        return {
            "name": self.name,
            "file": file_path,
            "method": self.method,
            "threshold": float(self.threshold),
            "roi_front": list(self.roi_front),
            "roi_back": list(self.roi_back),
            "scale_range": scale_range,
            "scale_step": float(self.scale_step),
        }

    def _apply_match_result(self, result: dict) -> bool:
        if result.get("matched"):
            roi_front = result.get("roi_front")
            if roi_front is not None:
                self.roi_front = [int(v) for v in roi_front]
            return True
        return False

    def template_match(self, image: np.array, threshold: float = None) -> bool:
        if threshold is None:
            threshold = self.threshold
        source = self.corp(image)
        mat = self.image

        if self._template_image_invalid(mat):
            return True  # 如果模板图像无效，直接返回 True

        res = cv2.matchTemplate(source, mat, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if self.debug_mode:
            logger.attr(self.name, f'matching score {max_val:.5f}')

        if max_val > threshold:
            self._update_roi_front(max_loc, (mat.shape[1], mat.shape[0]))
            return True
        return False

    def _get_multi_scale_range(self) -> tuple[float, float, float]:
        active_scale_range = self.scale_range
        if active_scale_range is None:
            min_scale, max_scale = self.DEFAULT_MULTI_SCALE_RANGE
            step = self.DEFAULT_MULTI_SCALE_STEP
        elif len(active_scale_range) == 3:
            min_scale, max_scale, step = active_scale_range
        else:
            min_scale, max_scale = active_scale_range
            step = self.scale_step
        if min_scale > max_scale:
            min_scale, max_scale = max_scale, min_scale
        if step <= 0:
            step = self.DEFAULT_MULTI_SCALE_STEP
        return min_scale, max_scale, step

    def multi_scale_template_match(self, image: np.array, threshold: float = None) -> bool:
        if threshold is None:
            threshold = self.threshold
        source = self.corp(image)
        mat = self.image

        if self._template_image_invalid(mat):
            return True  # 如果模板图像无效，直接返回 True

        min_scale, max_scale, step = self._get_multi_scale_range()
        best_val = -1.0
        best_loc = None
        best_shape = None
        cur_scale = min_scale
        while cur_scale <= max_scale + 1e-8:
            scaled_w = max(1, int(mat.shape[1] * cur_scale))
            scaled_h = max(1, int(mat.shape[0] * cur_scale))
            if scaled_w > source.shape[1] or scaled_h > source.shape[0]:
                cur_scale += step
                continue
            scaled_mat = cv2.resize(mat, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)
            res = cv2.matchTemplate(source, scaled_mat, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_shape = (scaled_w, scaled_h)
            cur_scale += step
        if self.debug_mode:
            logger.attr(self.name, f'multi-scale matching score {best_val:.5f}')
        if best_loc is not None and best_shape is not None and best_val > threshold:
            self._update_roi_front(best_loc, best_shape)
            return True
        return False

    def match(self, image: np.array, threshold: float = None, frame_id: str = None) -> bool:
        """
        :param threshold:
        :param image:
        :return:
        """
        client = get_image_client()
        result = client.match_rule(
            rule_data=self.to_service_payload(),
            image=image,
            frame_id=frame_id,
            threshold=threshold,
        )
        return self._apply_match_result(result)

    def match_all(self, image: np.array, threshold: float = None, roi: list = None, frame_id: str = None) -> list[tuple]:
        """
        区别于match，这个是返回所有的匹配结果
        :param roi:
        :param image:
        :param threshold:
        :return:
        """
        if roi is not None:
            self.roi_back = roi
        client = get_image_client()
        result = client.match_all(
            rule_data=self.to_service_payload(),
            image=image,
            frame_id=frame_id,
            threshold=threshold,
            roi=self.roi_back,
        )
        return [tuple(item) for item in result.get("matches", [])]

    def match_all_any(self, image: np.array, threshold: float = None, roi: list = None, nms_threshold: float = 0.3, frame_id: str = None) -> list[tuple]:
        """
        区别于match，这个是返回所有的匹配结果，去除冗余匹配项（例如：多个框选区域重叠的情况）时使用。
        :param roi:
        :param image:
        :param threshold:
        :return:
        """
        if roi is not None:
            self.roi_back = roi
        client = get_image_client()
        result = client.match_all_any(
            rule_data=self.to_service_payload(),
            image=image,
            frame_id=frame_id,
            threshold=threshold,
            roi=self.roi_back,
            nms_threshold=nms_threshold,
        )
        return [tuple(item) for item in result.get("matches", [])]

    def coord(self) -> tuple:
        """
        获取roi_front的随机的点击的坐标
        :return:
        """
        x, y, w, h = self.roi_front
        return x + np.random.randint(0, w), y + np.random.randint(0, h)

    def coord_more(self) -> tuple:
        """
         获取roi_back的随机的点击的坐标
        :return:
        """
        x, y, w, h = self.roi_back
        return x + np.random.randint(0, w), y + np.random.randint(0, h)

    def front_center(self) -> tuple:
        """
        获取roi_front的中心坐标
        :return:
        """
        x, y, w, h = self.roi_front
        return int(x + w//2), int(y + h//2)

    def test_match(self, image: np.array):
        self.debug_mode = True
        if self.is_template_match:
            return self.match(image)
        if self.is_multi_scale_template_match:
            return self.match(image)
        if self.is_sift_flann:
            return self.sift_match(image, show=True)

    def sift_match(self, image: np.array, show=False) -> bool:
        """
        特征匹配，同样会修改 roi_front
        :param image: 是游戏的截图，就是转通道后的截图
        :param show: 测试用的
        :return:
        """
        source = self.corp(image)
        kp, des = self.sift.detectAndCompute(source, None)
        # 参数1：index_params
        #    对于SIFT和SURF，可以传入参数index_params=dict(algorithm=FLANN_INDEX_KDTREE, trees=5)。
        #    对于ORB，可以传入参数index_params=dict(algorithm=FLANN_INDEX_LSH, table_number=6, key_size=12）。
        index_params = dict(algorithm=1, trees=5)
        # 参数2：search_params 指定递归遍历的次数，值越高结果越准确，但是消耗的时间也越多。
        search_params = dict(checks=50)
        # 根据设置的参数创建特征匹配器 指定匹配的算法和kd树的层数,指定返回的个数
        flann = cv2.FlannBasedMatcher(index_params, search_params)
        # 利用创建好的特征匹配器利用k近邻算法来用模板的特征描述符去匹配图像的特征描述符，k指的是返回前k个最匹配的特征区域
        # 返回的是最匹配的两个特征点的信息，返回的类型是一个列表，列表元素的类型是Dmatch数据类型，具体是什么我也不知道
        # 第一个参数是小图的des, 第二个参数是大图的des
        matches = flann.knnMatch(self.des, des, k=2)

        good = []
        result = True
        for i, (m, n) in enumerate(matches):
            # 设定阈值, 距离小于对方的距离的0.7倍我们认为是好的匹配点.
            if m.distance < 0.7 * n.distance:
                good.append(m)
        if len(good) >= 8:
            src_pts = float32([self.kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

            # 计算透视变换矩阵m， 要求点的数量>=4
            m, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            # 创建一个包含模板图像四个角坐标的数组
            w, h = self.roi_front[2], self.roi_front[3]
            pts = float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
            if m is None:
                result = False
            else:
                dst = int32(cv2.perspectiveTransform(pts, m))
                self.roi_front[0] = dst[0, 0, 0] + self.roi_back[0]
                self.roi_front[1] = dst[0, 0, 1] + self.roi_back[1]
                if show:
                    cv2.polylines(source, [dst], isClosed=True, color=(0, 0, 255), thickness=2)
                if not is_approx_rectangle(np.array([pos[0] for pos in dst])):
                    result = False
        else:
            result = False

        # https://blog.csdn.net/cungudafa/article/details/105399278
        # https://blog.csdn.net/qq_45832961/article/details/122776322
        if show:
            # 准备一个空的掩膜来绘制好的匹配
            mask_matches = [[0, 0] for i in range(len(matches))]
            # 向掩膜中添加数据
            for i, (m, n) in enumerate(matches):
                if m.distance < 0.6 * n.distance:  # 理论上0.7最好
                    mask_matches[i] = [1, 0]
            img_matches = cv2.drawMatchesKnn(self.image, self.kp, source, kp, matches, None,
                                             matchColor=(0, 255, 0), singlePointColor=(255, 0, 0),
                                             matchesMask=mask_matches, flags=0)
            cv2.imshow(f'Sift Flann: {self.name}', img_matches)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return result

    def match_mean_color(self, image, color: tuple, bias=10) -> bool:
        """

        :param image:
        :param color:  rgb
        :param bias:
        :return:
        """
        image = self.corp(image)
        average_color = cv2.mean(image)
        # logger.info(f'{self.name} average_color: {average_color}')
        for i in range(3):
            if abs(average_color[i] - color[i]) > bias:
                return False
        return True


if __name__ == "__main__":
    from dev_tools.assets_test import detect_image

    IMAGE_FILE = './log/test/QQ截图20240223151924.png'
    from tasks.Restart.assets import RestartAssets
    jade = RestartAssets.I_HARVEST_JADE
    jade.method = 'Sift Flann'
    sign = RestartAssets.I_HARVEST_SIGN
    sign.method = 'Sift Flann'
    print(jade.roi_front)

    detect_image(IMAGE_FILE, jade)
    detect_image(IMAGE_FILE, sign)
    print(jade.roi_front)
