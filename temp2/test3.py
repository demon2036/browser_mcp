import google.generativeai as genai
import os

# 配置 API 密钥
# 您需要从 Google AI Studio 获取 API 密钥
# https://aistudio.google.com/app/apikey
genai.configure(api_key="AIzaSyBUKydu9MQ0MU8KezYUNX6hz2U32sGyXnU")

# 初始化 Gemini 2.0 Flash 模型
model = genai.GenerativeModel('gemini-2.5-flash')


# 简单文本生成示例
def generate_text(prompt):
    """生成文本响应"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"错误: {str(e)}"


# 流式响应示例
def generate_streaming(prompt):
    """流式生成文本响应"""
    try:
        response = model.generate_content(prompt, stream=True)
        full_response = ""
        for chunk in response:
            if chunk.text:
                print(chunk.text, end="")
                full_response += chunk.text
        return full_response
    except Exception as e:
        return f"错误: {str(e)}"


# 多轮对话示例
def chat_example():
    """多轮对话示例"""
    chat = model.start_chat(history=[])

    while True:
        user_input = input("\n您: ")
        if user_input.lower() in ['退出', 'exit', 'quit']:
            break

        response = chat.send_message(user_input)
        print(f"Gemini: {response.text}")


# 带参数的高级配置
def generate_with_config(prompt):
    """使用自定义参数生成"""
    generation_config = {
        "temperature": 0.9,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 2048,
    }

    safety_settings = [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_MEDIUM_AND_ABOVE"
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_MEDIUM_AND_ABOVE"
        }
    ]

    try:
        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        return response.text
    except Exception as e:
        return f"错误: {str(e)}"


# 主程序示例
if __name__ == "__main__":
    # 设置 API 密钥（请替换为您的密钥）
    # os.environ["GEMINI_API_KEY"] = "YOUR_API_KEY_HERE"

    # 示例 1: 简单文本生成
    print("=== 简单文本生成 ===")
    result = generate_text("。")
    print(result)

