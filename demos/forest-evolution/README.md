# 森林进化论 · Forest Evolution

在 4 × 4 棋盘上移动相同的森林动物。从瓢虫开始，合成狐狸、小鹿、大象和老虎，最终解锁戴着叶冠的狮子。图鉴与棋局进度保存在当前浏览器。

[在线游玩](https://fdd77931-arch.github.io/fl-portfolio/demos/forest-evolution/) · [作品集案例](https://fdd77931-arch.github.io/fl-portfolio/forest-evolution.html)

## 操作和进度

- 使用方向键、WASD、页面方向按钮，或在棋盘上拖动和滑动。
- 初始放置两只瓢虫。有效移动才生成一只低等级动物。发现毛毛虫后，每次生成有 10% 概率放置毛毛虫。
- 合并获得 `2 ** 新等级` 分。每枚棋子单步只合并一次。Lv. 11 达成通关，可继续玩至棋盘无步可走。
- 撤销恢复上一步之前的棋盘和本局得分。最高分、图鉴解锁和音效设置是跨局记录。重开清除本局棋盘和撤销状态。
- 默认关闭音效。减少动态效果的系统设置会保留玩法，关闭移动、出现和进化动画。

## 视觉设计

奶油纸色、橡木棋盘、森林绿按钮和固定位置的等级角标。桌面并排显示森林插画、棋盘与进化手账。窄屏先显示简化的标题区和可滑动棋盘，手账随内容下移。图鉴、游戏结束与最终进化各有独立的对话框。

森林场景和 11 个透明动物形象使用 OpenAI 内建 ImageGen 生成。动物按 4 × 3 图集生成后逐格裁切为透明 WebP。素材统一采用带纸张颗粒的水粉风格，形象细节从瓢虫逐步增加到叶冠狮子。素材保存在 `assets/`。作品集封面取自浏览器中的实际游戏画面。

操作规则参考经典 2048 的四向移动、合并和终局定义。游玩入口与作品集案例沿用原网站的静态路由和项目卡结构。 [2048 在线演示](https://play2048.co/) · [2048 项目](https://github.com/gabrielecirulli/2048) · [Zoo Forest 导览](https://zoo-forest.com/)

## 开发与测试

从作品集仓库根目录启动 HTTP 服务。浏览器模块以 HTTP 加载。

```sh
python3 -m http.server 8000 --bind 127.0.0.1
node --test demos/forest-evolution/tests/*.test.mjs
```

打开 [本地游戏](http://127.0.0.1:8000/demos/forest-evolution/) 或 [本地作品集](http://127.0.0.1:8000/)。Node.js 仅用于测试，网页由原生浏览器模块运行。

| 文件 | 职责 |
| --- | --- |
| `engine.mjs` | 纯棋盘规则、合并得分和随机生成 |
| `storage.mjs` | 游戏状态、撤销、存档校验与持久化 |
| `animals.mjs` | 等级、物种、色调、描述和素材路径 |
| `app.mjs` | 输入、渲染、移动动画和对话框 |
| `audio.mjs` | 用 Web Audio 合成反馈声音 |
| `tests/engine.test.mjs` | 规则、存档、撤销与边界用例 |

## 发布

作品集由 GitHub Pages 从 `main` 根目录发布。项目入口是 `index.html` 新增的游戏卡片和 `forest-evolution.html` 案例页。两处封面共用 `assets/forest-evolution-preview.webp`，并链接至 `demos/forest-evolution/`。新增的项目元数据位于 `projects.json`。
