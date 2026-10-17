# -*- coding: utf-8 -*-
"""pytest 入口补丁：把**仓库根**放进 sys.path。

为什么需要：测试都在 ``tests/`` 里，而 ``python -m pytest`` 只会把"当前工作目录"加进
``sys.path``。于是：
  * 在仓库根跑 ``python -m pytest -q``  —— 根就是 cwd，天然能找到 ``genshin_dmg`` / ``server``；
  * 在 ``tests/`` 里跑 ``python -m pytest`` —— cwd 是 tests，找不到包，收集阶段就报错。

这行补丁把仓库根补进去，两种跑法都一样（也方便编辑器/IDE 直接点单个文件的 Run）。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
