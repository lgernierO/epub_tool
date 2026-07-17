# TODO

记录日期：2026-07-17  
执行者：Codex / Murong Agent

## 字体处理：同一 font-family 下精确选择实际字体文件

### 状态

已完成首版落地：

- 新增 `python_backend/services/font_face_resolve.py`
- `font_encrypt` / `font_decrypt` 已保存结构化 `@font-face` 候选：
  - family
  - src 字体文件
  - font-weight
  - font-style
  - unicode-range
  - CSS 后声明顺序
- 正文映射改为字符级字体选择
- 定向单测见 `tests/test_font_face_resolve.py`

### 后续可继续增强

- 更完整的 CSS shorthand / 继承 weight-style 计算
- 把 encrypt/decrypt 中重复 CSS 解析逻辑进一步抽到共享模块
- 为 bold/italic/unicode-range 增加端到端 EPUB fixture 回归

## 任务控制

### 已完成

- 任务取消：前端“停止任务” + Rust `cancel_epub_task`（强制终止当前 worker）
- 有限并发：`task_concurrency`（默认 1，最大 4；仅非 OCR 任务）
- OCR 批推理：`recognize_batch` + `ocr_batch_size`

### 后续

- soft-cancel 双通道（避免仅硬杀进程）
- 失败项一键重试
- 更细的 OCR 字符级进度事件
