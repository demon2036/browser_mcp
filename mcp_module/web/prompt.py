"""提示词管理模块"""

# ========== 网页摘要提示词 ==========
WEB_SUMMARY_PROMPT = """你是一个专业的内容分析助手。请根据用户的查询需求，对以下网页内容进行精准摘要。

用户查询：{query}

网页内容：
{content}

要求：
1. 重点关注与用户查询相关的信息
2. 保持客观准确，不添加原文没有的信息
3. 摘要应该简洁明了，突出重点
4. 如果内容与查询无关，请明确说明

请提供摘要："""

# ========== 文档块选择提示词 ==========
CHUNK_SELECTION_PROMPT = """You are analyzing document chunks to find information relevant to a user query.

User Query: {query}

Document chunks:
{chunks_text}

Select up to {max_selections} chunks that are most relevant to answering the query.
Return ONLY a JSON array of chunk numbers, like: [0, 3, 7, 12]

Selection criteria:
- Direct relevance to the query
- Contains key information
- Provides context or evidence

Your response:"""

# ========== 最终筛选提示词 ==========
FINAL_SELECTION_PROMPT = """From these pre-selected relevant chunks, choose the {final_max} MOST important ones.

User Query: {query}

Selected chunks:
{chunks_text}

Return ONLY a JSON array of chunk numbers from the ones shown above.
Choose chunks that best answer the query with minimum redundancy.

Your response:"""