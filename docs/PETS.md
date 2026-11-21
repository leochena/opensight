# 宠物识别

OpenSight 除了人脸，还支持**宠物识别**：把你家猫狗的照片导入一个「宠物库」，摄像头识别到相似宠物时产生候选事件并走同样的告警链路。人脸库和宠物库**分别建库、分别识别、互不混比**。

## 已实测的真实模型

宠物识别默认使用 [open-noodle/pet-recognition](https://huggingface.co/open-noodle/pet-recognition-small) 的 ONNX 模型，**开箱即真实可用**（不是占位 mock）：

| 规格 | 值 |
|---|---|
| 模型 | open-noodle/pet-recognition-small（DINOv2 + 投影头） |
| 许可 | **Apache-2.0**（可商用，对公益/开源友好） |
| 输入 | 224×224 RGB，ImageNet 归一化 |
| 输出 | 512 维 L2 归一化 embedding，余弦相似度直接可比 |
| 权重大小 | small 89MB / base 348MB / large 1.2GB |

**首次运行会自动下载权重**到 `data/models/`（容器内 `/root/.cache/opensight/models`），之后完全离线。已通过本地实测：不同个体余弦相似度约 -0.17~0.18，猫狗区分明显。

识别准确率（模型卡公布，从未见过的个体 top-1）：

| 尺寸 | 狗 | 猫 | 大小 |
|---|---|---|---|
| small（默认） | 53.5% | 91.3% | 89MB |
| base | 61.2% | 91.6% | 348MB |
| large | 67.2% | 91.5% | 1.2GB |

> **现实预期**：狗的个体识别比猫难得多。这套模型适合"是不是我家那只"的小范围比对，不适合大范围识别。猫的效果很好。要更高狗识别率可换 base/large（见下）。

## 快速使用

1. Web 界面「比对库 → 新建比对库」，类型选 **🐾 宠物（猫狗识别）**
2. 选中该库，添加宠物：填名字、物种/品种（如「橘猫」「金毛」）、上传清晰照片
3. 摄像头关联该库（不填 `gallery_ids` 则关联所有库）
4. 命中后在「事件记录」查看，带 🐾 宠物标签

同一路摄像头可以同时关联人脸库和宠物库：worker 按库类型分组，分别调用对应引擎，不会把狗和人脸混在一起比。

## 配置

`config/config.yaml`：

```yaml
pets:
  enabled: true
  backend: pet-onnx        # pet-onnx（真实）| pet-mock（占位，仅测链路）
  model_size: small        # small / base / large
  model_path: ""           # 可选：直接指定本地 .onnx 文件，跳过下载
  threshold: 0.35          # 宠物阈值；该模型分数偏低，建议 0.25~0.45
```

人脸与宠物用**不同阈值**：人脸用 `recognition.threshold`（默认 0.6），宠物用 `pets.threshold`（默认 0.35）。因为宠物模型的相似度分布整体偏低，套用人脸阈值会漏报。

改完重启：`docker compose restart worker api`。

## 关于检测框

当前 `pet-onnx` 用**整帧特征**做比对，适合"背景干净、宠物占画面主体"的场景（门口、院子、宠物店柜台）。如果要像 Frigate 那样框出画面里的猫狗个体再识别，需要再接一层目标检测器（如 YOLO 的 cat/dog 类）——这是扩展点，用户可按需实现，不影响现有链路。

## 降级与离线

- 无网络时首次下载会失败，可手动把模型放进 `data/models/pet-recognition-small.onnx`，或用 `model_path` 指向本地文件
- 想完全零依赖跑通链路（比如 CI），把 `backend` 改成 `pet-mock`（占位，识别结果无意义）

## 合规提示

宠物照片同样可能涉及他人的个人信息与财产权益：

- 只导入你自己的宠物，或你有权处理的照片（家人宠物、已登记寄养）
- 不要收集、导入他人宠物照片用于跟踪、骚扰
- 设置显著告知标识（系统已在预览叠加提示）
- 宠物走失请联系当地宠物救助机构 / 物业，本工具仅作辅助提醒

## 数据兼容

- 新增字段对老数据库自动迁移（`galleries.kind`、`persons.species`、`events.subject_kind`），升级不丢数据
- 未指定类型的旧比对库默认为 `face`，行为与升级前一致
