# RAG 评测数据集

这个目录用于存放离线 RAG 评测数据，后续可以用来计算 `Hit Rate@5` 和 `Unsupported Claim Rate` 等指标。

## 文件放在哪里

- 评测样本写在 `cases.json`。
- 每个样本对应的资料文件放在 `materials/case_001/`、`materials/case_002/` 等目录下。
- `assignment_id` 建议使用评测专用区间，例如 `9001` 到 `9020`，避免和正常作业数据冲突。

## 样本格式

每个 case 表示一个作业评测样本，需要描述作业信息、要索引的资料文件，以及用于计算 `Hit Rate@5` 的期望证据。

```json
{
  "case_id": "case_001",
  "assignment_id": 9001,
  "title": "示例作业标题",
  "course": "示例课程",
  "description": "示例作业问题或要求。",
  "skill_id": "lab_report",
  "top_k": 5,
  "materials": [
    {
      "id": 900101,
      "filename": "example.md",
      "path": "agent-python/tests/fixtures/rag_eval/materials/case_001/example.md",
      "content_type": "text/markdown"
    }
  ],
  "gold_evidence": [
    {
      "filename": "example.md",
      "section_title": "期望命中的章节标题",
      "must_contain": ["关键词一", "关键词二"]
    }
  ]
}
```

## 字段说明

- `case_id`：评测样本编号，例如 `case_001`。
- `assignment_id`：评测专用作业 ID，用于创建 assignment-scoped Chroma collection。
- `title`：作业标题。
- `course`：课程名称，可以为空字符串。
- `description`：用户的作业说明或问题。
- `skill_id`：生成使用的业务技能，例如 `lab_report`、`paper_summary`、`course_qa_report`。
- `top_k`：检索返回数量，评测 `Hit Rate@5` 时保持为 `5`。
- `materials`：该样本需要索引的资料文件列表。
- `gold_evidence`：人工标注的期望证据，用来判断 top 5 检索结果是否命中。

## 资料文件要求

支持的资料格式：

- `.pdf`
- `.md`
- `.markdown`
- `.txt`

建议每个 case 使用独立目录，例如：

```text
materials/case_001/
  sort_lab.md
  notes.txt

materials/case_002/
  paper.pdf
```

然后在 `cases.json` 里填写相对路径：

```json
"path": "agent-python/tests/fixtures/rag_eval/materials/case_001/sort_lab.md"
```

## gold_evidence 怎么填

`gold_evidence` 不需要标注完整答案，只需要标注“检索前 5 条里应该至少命中的证据特征”。

例如：

```json
"gold_evidence": [
  {
    "filename": "sort_lab.md",
    "section_title": "实验结果",
    "must_contain": ["快速排序", "归并排序", "时间复杂度"]
  }
]
```

后续评测脚本可以用 `filename`、`section_title` 和 `must_contain` 来自动判断 `Hit Rate@5`。
