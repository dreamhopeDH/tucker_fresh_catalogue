# Historical specification: Tucker Fresh 100-product test MVP

> This document is retained as the historical Phase 1 specification and is no
> longer active. The production source of truth is `docs/PRODUCTION_SPEC.md`.
> Do not use the test-only limits or `test/` namespace below for production.

# Tucker Fresh 折扣广告册——100 件商品测试版开发任务书

## 1. 你的任务

请在一个新的 GitHub 仓库中，实现 Tucker Fresh 折扣广告册测试版。

商品来源：

`https://broadway.shop.tuckerfresh.com.au/specials`

本次只抓取并展示按网站原始顺序出现的前 **100 件唯一商品**。

测试版的目标不是制作临时演示代码，而是验证正式版的完整流程：

```text
抓取商品
→ 标准化数据
→ 合并清晰的同系列商品
→ 把模糊商品放在最后
→ 按促销条件拆分同系列成员
→ 慢速下载图片
→ 转换成 256 × 256 WebP
→ 上传 Backblaze B2
→ 生成手机版静态广告册
→ 部署到 Cloudflare Pages
```

测试完成后，正式版应主要通过修改配置把商品上限从 100 改为全部商品，而不是重写程序。

---

# 2. 核心开发原则

必须遵守以下原则：

1. 这是 MVP，不提前实现未来功能。
2. 代码应简单、直接、容易阅读。
3. 不要创建微服务、后端 API、数据库服务器或管理后台。
4. 不要因为未来可能需要某个功能，就提前创建复杂插件系统。
5. 只在明确需要替换的位置留下小型函数边界。
6. 每个模块只负责一个阶段。
7. 不使用大模型进行商品判断。
8. 抓取、分组、图片处理和前端展示必须彼此分离。
9. 测试版和未来正式版使用同一条处理流程。
10. 不得在代码中写死密钥。

若实现明显超过约 2,500 行，应重新检查是否出现过度设计。

---

# 3. 测试版范围

## 3.1 商品数量

测试版只处理前 100 件唯一商品。

配置：

```python
MAX_PRODUCTS = 100
```

抓取逻辑：

1. 从 specials 第一页开始。
2. 按网站原始排列顺序解析商品。
3. 使用网站商品 ID 去重；若无法取得 ID，则使用规范化后的商品详情 URL 去重。
4. 收集满 100 件后立即停止。
5. 不继续请求剩余分页。
6. 如果最后一个已请求页面包含超过所需数量的商品，只保留前 100 件。

未来正式版应支持：

```python
MAX_PRODUCTS = None
```

表示抓取全部商品。

不要为测试版编写另一套独立抓取器。

---

## 3.2 本次必须验证的功能

测试版必须实际验证：

* 商品分页抓取；
* 商品名称和价格解析；
* 商品系列分组；
* 模糊商品处理；
* 同系列促销条件拆分；
* 100 张图片慢速下载；
* 图片断点恢复；
* 图片 URL 未变化时跳过下载；
* 图片转换；
* B2 上传；
* 静态广告册生成；
* 手机左右翻页；
* Cloudflare Pages 部署；
* GitHub Actions 手动和定时运行。

---

# 4. 明确不实现的功能

测试版不得实现：

* 肉类、蔬菜等商品类别；
* 搜索；
* 收藏；
* 用户账号；
* 管理后台；
* 在线修改商品分组；
* PWA；
* Service Worker；
* 离线浏览；
* 原生 Android 应用；
* 复杂纸张翻页动画；
* 价格历史；
* 跨周价格比较；
* 多家超市；
* 大模型判断；
* PostgreSQL；
* Cloudflare Worker；
* Cloudflare D1；
* 图片 ETag 检查；
* Last-Modified 检查；
* 图片内容 hash 变化检查；
* 图片放大；
* 高分辨率图片版本；
* 自动商品分类；
* 自制通用 ORM 或依赖注入框架。

---

# 5. 技术栈

## Python

使用：

```text
Python 3.12
httpx
BeautifulSoup4
RapidFuzz
Pillow
PyYAML
boto3
pytest
```

## 前端

使用：

```text
Vite
原生 TypeScript
HTML
CSS
```

不要使用 React、Vue、Svelte 或其他前端框架。

本项目当前页面逻辑不复杂，原生 TypeScript 足够。

## 基础设施

```text
GitHub：代码仓库
GitHub Actions：定时执行
Backblaze B2：图片和图片 manifest
Cloudflare Pages：静态网站
```

---

# 6. 推荐目录结构

保持以下结构，不要额外拆成大量小文件：

```text
project/
├── src/
│   ├── models.py
│   ├── config.py
│   ├── scrape.py
│   ├── normalize.py
│   ├── grouping.py
│   ├── offers.py
│   ├── images.py
│   ├── b2_store.py
│   ├── catalogue.py
│   └── main.py
│
├── config/
│   ├── grouping_rules.yml
│   └── manual_overrides.yml
│
├── web/
│   ├── index.html
│   ├── src/
│   │   ├── main.ts
│   │   └── styles.css
│   ├── public/
│   │   ├── favicon.ico
│   │   └── icon-192.png
│   └── package.json
│
├── tests/
│   ├── fixtures/
│   ├── test_normalize.py
│   ├── test_grouping.py
│   ├── test_offers.py
│   └── test_image_change.py
│
├── output/
│   └── .gitkeep
│
├── .github/
│   └── workflows/
│       └── update-catalogue.yml
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

`output/` 保存运行期间生成的 JSON 和前端数据，但生成内容不应提交到 Git 历史。

---

# 7. 配置设计

集中在 `src/config.py` 中读取环境变量。

至少支持以下配置：

```text
SOURCE_SPECIALS_URL
MAX_PRODUCTS
PAGE_SIZE

LIST_PAGE_DELAY_MIN_SECONDS
LIST_PAGE_DELAY_MAX_SECONDS

IMAGE_DELAY_MIN_SECONDS
IMAGE_DELAY_MAX_SECONDS
IMAGE_TIMEOUT_SECONDS
IMAGE_MAX_ATTEMPTS

B2_ENDPOINT
B2_KEY_ID
B2_APPLICATION_KEY
B2_BUCKET
B2_PREFIX

CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
CLOUDFLARE_PAGES_PROJECT
```

测试版默认值：

```text
SOURCE_SPECIALS_URL=https://broadway.shop.tuckerfresh.com.au/specials
MAX_PRODUCTS=100
PAGE_SIZE=9

LIST_PAGE_DELAY_MIN_SECONDS=3
LIST_PAGE_DELAY_MAX_SECONDS=6

IMAGE_DELAY_MIN_SECONDS=5
IMAGE_DELAY_MAX_SECONDS=8
IMAGE_TIMEOUT_SECONDS=30
IMAGE_MAX_ATTEMPTS=3

B2_PREFIX=test
```

图片请求必须：

* 并发数固定为 1；
* 每次图片请求后随机等待 5～8 秒；
* 重试请求也必须受限速控制；
* 不得为了加速开启并发。

这些数字必须是配置，而不是散落在下载函数中。

未来正式版如果需要更长间隔或分批运行，应只修改配置或增加批次参数。

---

# 8. 商品数据模型

使用 Python `dataclass`。

## RawProduct

保存网页直接解析的内容：

```python
@dataclass
class RawProduct:
    source_product_id: str | None
    name: str
    product_url: str
    image_url: str | None
    regular_price_cents: int | None
    special_price_cents: int | None
    saving_cents: int | None
    offer_text: str | None
    scraped_at: str
    source_order: int
```

## Product

保存标准化结果：

```python
@dataclass
class Product:
    product_id: str
    raw_name: str
    normalized_name: str
    product_url: str
    image_url: str | None
    brand_hint: str | None
    size_text: str | None
    family_stem: str
    variant_hint: str | None
    regular_price_cents: int | None
    special_price_cents: int | None
    saving_cents: int | None
    normalized_offer_text: str
    source_order: int
    category_id: str | None = None
```

`category_id` 只保留字段，不实现分类逻辑。

## GroupingResult

```python
@dataclass
class GroupingResult:
    confirmed_families: list[ProductFamily]
    standalone_products: list[Product]
    uncertain_products: list[UncertainProduct]
```

不要使用数据库。

---

# 9. 网页抓取

## 9.1 请求方式

使用 `httpx.Client`：

* 复用连接；
* 设置合理 User-Agent；
* 支持重定向；
* 超时；
* 对临时错误做有限重试。

User-Agent 示例：

```text
PersonalTuckerCatalogue/0.1
```

不要：

* 随机伪装多个浏览器；
* 使用代理池；
* 使用 Playwright；
* 模拟点击；
* 绕过验证码；
* 绕过登录；
* 并发抓取分页。

## 9.2 分页限速

分页请求必须单线程。

每个新的列表页请求后随机等待 3～6 秒。

如果第一页已经包含足够商品，不应继续请求其他页。

## 9.3 解析字段

尽可能从商品卡片直接解析：

* 商品 ID；
* 名称；
* 商品详情 URL；
* 图片 URL；
* 原价；
* 特价；
* 节省金额；
* 促销文字。

仅当列表页无法取得必要字段时，才考虑访问商品详情页。

不要默认对 100 件商品分别请求 100 个详情页。

## 9.4 抓取失败

* 某个商品解析失败时，记录日志并继续；
* 整个页面结构无法识别时，应明确失败；
* 不允许悄悄生成空广告册；
* 最终商品少于预期时，在 Action summary 中标记警告。

保存：

```text
output/raw-products.json
```

用于调试。

---

# 10. 名称标准化

在 `normalize.py` 中实现。

至少处理：

* 转小写；
* Unicode 撇号统一；
* 去除无意义标点；
* 合并多余空格；
* 提取重量和包装规格；
* 保留原始名称；
* 将价格全部保存为整数 cents。

规格至少支持常见形式：

```text
170g
1kg
1.5kg
375ml
1L
2 x 100g
6pk
12 pack
24 x 375ml
```

不要为了覆盖全部世界商品格式编写庞大解析器。

无法识别时返回 `None`。

---

# 11. 商品系列分组

采用保守策略。

宁可少合并，也不要错误合并。

## 11.1 判断顺序

```text
人工规则
→ 明确的规则分组
→ 相似候选判断
→ standalone 或 uncertain
```

人工规则优先级最高。

## 11.2 明确分组

确认合并的最低条件：

1. 规格相同；
2. 移除规格和已知口味词后，系列主体完全相同；
3. 没有人工排除规则。

例如：

```text
Smith's Crinkle Cut Chips BBQ 170g
Smith's Crinkle Cut Chips Chicken 170g
```

移除：

```text
BBQ
Chicken
170g
```

后得到相同 `family_stem`，可以标记为 `confirmed`。

## 11.3 模糊分组

若：

* 规格相同；
* 名称高度相似；
* 但 `family_stem` 不完全相同；

则进入 `uncertain`。

可以使用 RapidFuzz，但相似度阈值放在配置或模块常量中。

建议初始值：

```text
UNCERTAIN_SIMILARITY_THRESHOLD=82
```

不要仅凭相似度直接确认合并。

## 11.4 独立商品

不存在可靠候选的商品标记为 `standalone`，正常显示在主区域。

不要把所有未成功分组的商品都放入 uncertain。

## 11.5 人工规则

`config/manual_overrides.yml` 至少支持：

```yaml
merge: []
exclude: []
```

结构保持简单。

不制作复杂规则语言。

---

# 12. 促销条件拆分

系列确认完成后，在 `offers.py` 中按促销条件拆分。

促销键：

```python
promotion_key = (
    regular_price_cents,
    special_price_cents,
    normalized_offer_text,
)
```

不处理 `member_only`。

同一个商品系列中：

* 促销键相同的口味可以共用一个价格区块；
* 促销键不同的口味必须分开显示。

价格缺失的商品不得与有明确价格的商品共用价格标签。

商品系列关系和本周促销分组必须是两个独立概念。

---

# 13. 图片同步

## 13.1 测试版图片数量

测试版最多处理前 100 件商品对应的图片。

若多个商品没有图片 URL：

* 不请求；
* 使用统一占位图；
* 记录 `missing`。

## 13.2 URL 变化判断

只实现：

```python
def image_has_changed(
    previous_url: str | None,
    current_url: str | None,
) -> bool:
    return previous_url != current_url
```

规则：

```text
manifest 中无记录
→ 下载

URL 相同且状态为 downloaded
→ 跳过

URL 改变
→ 下载新图

URL 为空
→ missing
```

不要实现 ETag、Last-Modified 或图片内容 hash。

函数必须独立，方便未来替换。

## 13.3 图片下载速度

图片并发必须固定为 1。

每次请求之后随机等待：

```text
5～8 秒
```

包括：

* 成功请求；
* 下载失败；
* 重试请求。

不要在开始请求前等待后又在结束后重复等待，只需要保证相邻请求之间至少有配置的等待时间。

## 13.4 重试策略

最多 3 次尝试。

建议：

```text
第一次失败
→ 等待正常图片间隔，再重试

第二次失败
→ 额外等待 30 秒，再重试

第三次失败
→ 标记 failed，不阻塞整个构建
```

遇到：

```text
429
```

优先遵守 `Retry-After`。

没有 `Retry-After` 时至少等待 300 秒。

遇到 404：

* 直接标记 missing；
* 不进行三次重复请求。

连续 10 张图片失败时：

* 停止图片下载阶段；
* 保留已经完成的进度；
* 广告册继续使用占位图；
* 在 Action summary 中明确标记。

## 13.5 图片处理

使用 Pillow：

1. 读取图片；
2. 自动纠正方向；
3. 转换成 RGB 或 RGBA；
4. 保持比例缩放；
5. 放进 256 × 256 画布；
6. 商品居中；
7. 不裁掉商品主体；
8. 输出 WebP；
9. quality 设为 78；
10. 移除不必要元数据。

不要保留原始图片副本到 B2。

## 13.6 B2 object key

测试版使用：

```text
test/products/{product_id}/{image_url_hash}.webp
```

`image_url_hash` 可以取 URL SHA-256 的前 16 个十六进制字符。

占位图可以随前端部署，不需要放在 B2。

---

# 14. B2 存储

使用 Backblaze B2 的 S3-compatible API 和 `boto3`。

实现一个很小的 `B2ImageStore`：

```python
class B2ImageStore:
    def download_manifest(self) -> dict: ...
    def upload_manifest(self, manifest: dict) -> None: ...
    def upload_image(
        self,
        local_path: Path,
        object_key: str,
    ) -> None: ...
```

不要创建通用存储插件框架。

未来更换存储时，只需要保持这三个操作的调用边界。

测试版 manifest：

```text
test/state/image-manifest.json
```

manifest 示例：

```json
{
  "product-123": {
    "source_image_url": "https://example.com/image.jpg",
    "object_key": "test/products/product-123/abc123.webp",
    "status": "downloaded",
    "updated_at": "2026-08-05T01:00:00+08:00"
  }
}
```

每完成一张图片，应更新内存中的 manifest。

为实现断点恢复，manifest 应定期上传到 B2。

测试版可以每完成 5 张图片上传一次，并在图片阶段结束时再上传一次。

这样即使 Action 中断，也不需要从第一张重新下载。

图片对象设置：

```text
Content-Type: image/webp
Cache-Control: public, max-age=31536000, immutable
```

因为 URL 改变会生成新的 object key，可以使用 immutable 缓存。

---

# 15. 广告册数据输出

不要生成一个包含所有未来商品的大型 HTML 文件。

生成：

```text
output/site/
├── index.html
├── assets/
├── icons/
└── data/
    ├── manifest.json
    └── pages/
        ├── 1.json
        ├── 2.json
        └── ...
```

测试版每页默认 9 个展示单元。

注意：

* 一个促销一致的已合并商品系列算一个展示单元；
* 同一系列的不同促销组分别成为展示单元，并按各自折扣分类；
* standalone 商品算一个展示单元；
* uncertain 商品进入自己的折扣组，但排在该组 confirmed/standalone 商品之后。

展示单元按下列折扣组依次输出：

1. `over_50`：折扣大于 50%；
2. `exactly_50`：折扣正好等于 50%；
3. `forty_to_under_50`：折扣大于等于 40% 且小于 50%；
4. `under_40`：折扣小于 40%。

分类使用 `regular_price_cents` 和 `special_price_cents` 的整数比较，不使用
`saving_cents`。每个折扣组独立按 9 个展示单元分页，因此折扣组结束时允许页面未填满，
下一个非空折扣组必须从新页面开始。组内 confirmed/standalone 和 uncertain 各自保留
`source_order`；无法安全计算折扣的商品以 `discount_percent: null` 放到 `under_40`
相应类型的末尾。

`manifest.json` 示例：

```json
{
  "generated_at": "2026-08-05T01:00:00+08:00",
  "source_product_count": 100,
  "display_item_count": 82,
  "page_size": 9,
  "page_count": 11,
  "discount_groups": [
    {
      "id": "over_50",
      "label": "More than 50% off",
      "item_count": 10,
      "start_page": 1,
      "page_count": 2
    }
  ],
  "pages": [
    "data/pages/1.json",
    "data/pages/2.json"
  ]
}
```

每个页面 JSON 明确包含 `discount_group` 和 `discount_group_label`，浏览器不重新计算折扣组。

页面数据中图片只保存：

```text
image_key
```

前端通过同源的 Cloudflare Pages Function 路由：

```text
"/images/" + image_key
```

生成图片 URL。Pages Function 使用独立的只读 B2 凭证签名私有 bucket 的 S3-compatible GET 请求。

不要把 B2 endpoint、bucket 名或任何 B2 凭证写入 catalogue JSON 或浏览器 JavaScript。

---

# 16. 手机广告册页面


## 16.1 视觉参考

使用以下文件作为广告册的主要视觉参考：

`docs/reference/catalogue-layout.png`

参考图定义的是整体布局方向，而不是要求逐像素复制，也不要复制其他零售商的名称、Logo、商标或专属品牌元素。

广告册采用通用超市促销目录风格：

- 鲜黄色页面背景；
- 黄色卡片间距和页面边框；
- 白色商品卡片；
- 轻微圆角；
- 大面积商品图片；
- 红色圆形促销价格标签；
- 与价格标签相连或紧邻的黄色节省金额标签；
- 商品名称和补充价格信息放在卡片底部；
- 页面整体紧凑、整齐、容易快速浏览。

颜色必须使用 CSS custom properties 集中定义，方便以后统一替换。

示例：

```css
:root {
  --catalogue-yellow: #ffd900;
  --price-red: #ed1c24;
  --card-background: #ffffff;
  --text-primary: #111111;
}

## 16.2 翻页

使用横向页面容器和 CSS scroll-snap。

必须支持：

* 手指左右滑动；
* 上一页按钮；
* 下一页按钮；
* 当前页码；
* 页码输入或选择跳转；
* 回到第一页；
* 浏览器刷新后恢复上次页码。

页码保存到：

```text
localStorage
```

不制作 PWA，不注册 Service Worker。

## 16.3 页面加载

前端先读取：

```text
data/manifest.json
```

然后生成轻量 page shell。

使用 `IntersectionObserver`：

* 当前页面附近才请求对应 page JSON；
* 图片使用 `loading="lazy"`；
* 远离当前页的商品内容可以清空，以控制 DOM 大小；
* 页面 shell 可以保留。

测试版只有约十几页，但实现不能假设永远只有十几页。

未来约 4,000 件商品时，仍不能一次把所有商品卡片加入 DOM。

## 16.4 图片失败

图片加载失败时切换到本地占位图。

不得让一张图片错误破坏整页。

## 16.5 普通主屏幕快捷方式

不实现 PWA。

只需提供：

```text
favicon.ico
icon-192.png
```

网站应能被 Android 浏览器通过“添加到主屏幕”作为普通快捷方式保存。

不要添加：

* manifest.webmanifest；
* Service Worker；
* install prompt；
* standalone display 模式。

---

# 17. GitHub Actions

创建：

```text
.github/workflows/update-catalogue.yml
```

支持：

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "17 20 * * 0"
```

该 cron 对应珀斯时间星期一凌晨 4:17。

测试版仍然保持：

```text
MAX_PRODUCTS=100
B2_PREFIX=test
```

workflow 步骤：

1. Checkout。
2. 安装 Python 3.12。
3. 安装 Python dependencies。
4. 安装 Node.js。
5. 安装前端 dependencies。
6. 运行 pytest。
7. 运行 Python 抓取和构建程序。
8. 构建 Vite 静态网站。
9. 上传必要的调试输出为 GitHub Actions artifact。
10. 使用 Wrangler 部署 Cloudflare Pages。
11. 写入 GitHub Actions job summary。

需要上传的调试 artifact：

```text
raw-products.json
normalized-products.json
grouping-result.json
catalogue-manifest.json
```

不要上传原始商品图片到 GitHub artifact。

## Action summary

至少输出：

```text
请求的商品上限
实际抓取商品数
确认系列数量
独立商品数量
模糊商品数量
新下载图片数
跳过图片数
缺失图片数
失败图片数
最终页面数量
Cloudflare Pages 部署结果
```

---

# 18. GitHub Secrets

README 中说明 GitHub Actions 需要配置：

```text
B2_KEY_ID
B2_APPLICATION_KEY
CLOUDFLARE_API_TOKEN
```

GitHub Actions Variables：

```text
B2_ENDPOINT
B2_BUCKET
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_PAGES_PROJECT=tucker-catalogue-test
```

Cloudflare Pages runtime plaintext Variables `B2_ENDPOINT`、`B2_BUCKET` 定义在 Wrangler 配置的 `vars` 中。Cloudflare Dashboard 只配置独立只读的 Encrypted Secrets：`B2_READ_KEY_ID`、`B2_READ_APPLICATION_KEY`。不要把这两个 secret 写入 Wrangler 配置。

B2 bucket 必须保持 private。Cloudflare Pages 运行时不得复用 GitHub Actions 的读写 B2 凭证。

不要在日志中输出密钥、Authorization header 或完整连接配置。

---

# 19. 测试要求

使用 pytest。

至少覆盖：

## 名称标准化

* 大小写；
* 标点；
* 重量；
* 包装数量；
* 多余空格。

## 商品分组

* 相同系列不同口味可以确认合并；
* 不同规格不得自动合并；
* 名称相似但不完全明确时进入 uncertain；
* 独立商品保持 standalone；
* 人工排除规则覆盖自动规则。

## 促销拆分

* 原价和特价相同的成员共用促销区块；
* 特价不同必须拆分；
* 原价不同必须拆分；
* offer text 不同必须拆分；
* 缺失价格不得与完整价格合并。

## 图片变化

```text
旧 URL = 新 URL
→ False

旧 URL != 新 URL
→ True

无旧记录
→ True
```

## 图片转换

* 输出确实为 WebP；
* 画布为 256 × 256；
* 保持商品比例；
* 不因透明图片失败。

单元测试不要依赖实时网站。

---

# 20. 日志和错误处理

使用 Python 标准 `logging`。

日志应清楚展示当前阶段：

```text
SCRAPE
NORMALIZE
GROUP
SYNC_IMAGES
BUILD_CATALOGUE
DEPLOY
```

不要打印每一个普通内部变量。

每张图片可以记录简洁状态：

```text
[23/100] downloaded
[24/100] skipped
[25/100] missing
```

严重错误必须：

* 给出明确原因；
* 使用非零退出码；
* 不部署明显损坏或空的广告册。

图片部分的个别失败不是整体致命错误，应使用占位图继续构建。

---

# 21. README 必须包含

README 需要说明：

1. 项目用途；
2. 当前测试版只处理 100 件商品；
3. 本地运行方法；
4. 环境变量；
5. GitHub Secrets；
6. B2 bucket 配置；
7. Cloudflare Pages 项目配置；
8. 手动运行 GitHub Action 的方法；
9. 如何查看 Action artifact；
10. 如何修改 `MAX_PRODUCTS`；
11. 如何修改图片下载间隔；
12. 如何添加人工分组规则；
13. 如何清空测试数据；
14. 哪些功能明确不在测试版范围内。

本地运行示例：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd web
npm install
cd ..

python -m src.main
cd web
npm run dev
```

Windows 命令应在 README 中另外给出。

---

# 22. 核心执行入口

`src/main.py` 应保持清楚：

```python
def main() -> None:
    raw_products = fetch_specials(
        max_products=settings.max_products,
    )

    products = normalize_products(raw_products)

    grouping_result = group_products(
        products=products,
        rules=load_grouping_rules(),
        overrides=load_manual_overrides(),
    )

    offer_groups = split_families_by_promotion(
        grouping_result.confirmed_families,
    )

    image_manifest = sync_images(
        products=products,
        store=b2_store,
        settings=settings,
    )

    catalogue = build_catalogue(
        confirmed_offer_groups=offer_groups,
        standalone_products=grouping_result.standalone_products,
        uncertain_products=grouping_result.uncertain_products,
        image_manifest=image_manifest,
        page_size=settings.page_size,
    )

    write_catalogue_files(
        catalogue=catalogue,
        output_directory=settings.site_data_directory,
    )
```

不要把全部逻辑写进 `main.py`。

也不要创建多层 service、manager、handler、provider 包装。

---

# 23. 为正式版保留的有限扩展点

只保留以下扩展点。

## 商品上限

测试版：

```text
MAX_PRODUCTS=100
```

正式版：

```text
MAX_PRODUCTS=
```

或 `None`。

## 商品分类

未来可以在分组后加入：

```python
categorized = categorize_products(grouping_result)
```

当前不实现。

## 图片变化判断

当前：

```python
old_url != new_url
```

以后可以在同一个函数中加入 ETag 或 hash。

当前不实现。

## 图片存储

当前为 `B2ImageStore`。

前端只使用同源 `/images/` 路由和 `image_key`。

## 分组算法

当前为保守规则。

未来可以增加更多口味词、品牌规则或大模型辅助，但不能改变输出数据结构。

## 页面布局

当前固定两列卡片和每页 8 个展示单元。

未来可以加入分类页或桌面双页，不改变商品数据结构。

不要创建更多抽象扩展点。

---

# 24 真实集成验证流程

实现和验收分为两个阶段。

## Phase 1：本地和模拟验证

Codex 在没有真实云端凭证的情况下完成代码实现。

必须：

- 所有外部配置通过环境变量读取；
- B2 操作使用 mock 或 fake client 测试；
- 使用 fixture 商品数据构建前端；
- 运行 pytest；
- 运行 TypeScript 检查；
- 运行前端 production build；
- 明确说明 B2 和 Cloudflare 的真实集成尚未验证。

模拟测试通过，不代表真实 B2 上传或 Cloudflare Pages 部署已经成功。

Codex 不得仅凭 mock 测试声称云端部署完成。

## Phase 2：真实端到端验证

Phase 2 需要仓库所有者进行明确操作。

仓库所有者需要：

1. 在 GitHub 配置要求的 Secrets 和 Variables；
2. 从 GitHub Actions 页面手动启动 `workflow_dispatch`；
3. 等待真实工作流完成；
4. 打开部署后的 Cloudflare Pages 网站检查结果。

GitHub Actions 的真实工作流必须完成：

- 从 B2 下载或创建图片 manifest；
- 抓取前 100 件商品；
- 慢速下载测试图片；
- 转换成 256 × 256 WebP；
- 上传图片到 B2；
- 更新 B2 manifest；
- 构建广告册；
- 部署到 Cloudflare Pages。

Codex 不会在 Secrets 设置完成后自动恢复先前任务。

仓库所有者可以另外创建一个 Codex 后续任务，要求 Codex尝试启动和监控 GitHub Action，但这取决于 Codex环境是否具备：

- GitHub CLI；
- GitHub认证；
- 仓库写入权限；
- 网络权限。

这不是 MVP 成功的必要条件。

如果真实工作流失败：

- 保留 GitHub Actions 日志；
- 将错误日志交给 Codex；
- 或启动新的 Codex任务，让它检查和修复；
- 修复后再次手动运行工作流。

只有真实 GitHub Actions 工作流成功完成后，才可以认为 B2 和 Cloudflare Pages 集成已经验证。

# 25. 测试版验收标准

只有以下全部满足，测试版才算完成：

1. 手动运行 GitHub Action 可以成功完成。
2. 定时 workflow 已配置。
3. 程序只抓取前 100 件唯一商品。
4. 收集满 100 件后不再请求后续分页。
5. 原始商品顺序得到保留。
6. 清晰的不同口味商品可以合并。
7. 模糊商品进入最后的 uncertain 区域。
8. 独立商品正常出现在主区域。
9. 同系列不同促销价格会拆分显示。
10. 不处理 member-only 条件。
11. 图片并发固定为 1。
12. 相邻图片请求间随机等待 5～8 秒。
13. 图片转换成 256 × 256 WebP。
14. 图片上传到 B2 的 `test/` 前缀。
15. 图片 URL 未改变时，第二次运行不会重新下载。
16. Action 中断后可以根据 B2 manifest 继续。
17. 图片失败时广告册仍可生成，并显示占位图。
18. Cloudflare Pages 成功部署。
19. Android 手机可使用手指左右翻页。
20. 手机使用两列商品卡片。
21. 上一页、下一页和跳页功能正常。
22. 浏览器刷新后可以恢复阅读页码。
23. 只加载当前页附近的数据和图片。
24. 网站没有 PWA 或 Service Worker。
25. Android 浏览器可以将网站添加为普通主屏幕快捷方式。
26. pytest 全部通过。
27. README 包含完整部署与运行说明。
28. 不存在后台 API、数据库服务器或多余框架。

---

# 26. 交付要求

完成后请提供：

1. 实现摘要；
2. 文件结构；
3. 本地运行命令；
4. GitHub Secrets 列表；
5. 首次 GitHub Action 运行步骤；
6. 测试结果；
7. 已知限制；
8. 100 件测试版与未来正式版之间需要修改的配置项；
9. 不要声称已经成功部署，除非实际部署命令和 Action 确实成功；
10. 不要自行扩大功能范围。

完成前，Codex 必须使用本地 fixture 数据生成实际广告册页面。

Codex 应检查：

- 页面是否固定为 3×3；
- 手机视口下是否保持完整九宫格；
- 价格标签是否覆盖在图片区域左下方附近；
- 商品名称是否超出卡片；
- 两张或三张系列图片是否能正常并排；
- 长商品名称是否破坏卡片高度；
- 缺图占位图是否维持布局；
- 页面左右滑动是否正常；
- 页面是否意外产生横向溢出。

如果开发环境支持浏览器截图，至少生成一个常见 Android 手机尺寸的页面截图作为调试产物。

建议测试视口：

```text
360 × 800
390 × 844
412 × 915

本次优先保证：

```text
流程完整
结果可见
手机可用
源网站负荷低
代码容易扩展
```

不要优先追求复杂视觉设计。
