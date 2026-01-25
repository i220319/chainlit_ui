import chainlit as cl
import asyncio
import threading
from typing import Dict, Optional
from test_client import analyze_logs_stream
# 1. 模拟的Yield函数 (Mock Yield Function)
async def process_input(text: str, files: Optional[list] = None):
    """
    Simulates a processing function that yields status and final content.
    Yields:
        dict: {"status": "..."} for intermediate steps
        dict: {"content": "..."} for the final result
    """
    
    # 1. Prepare file paths
    file_paths = []
    if files:
        for f in files:
            if hasattr(f, "path"):
                file_paths.append(f.path)
            else:
                file_paths.append(str(f))

    # 2. Bridge Sync Generator to Async Iterator using Thread + Queue
    # This prevents the blocking 'requests' call from freezing the main event loop
    q = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def producer():
        try:
            for item in analyze_logs_stream(text, file_paths):
                loop.call_soon_threadsafe(q.put_nowait, item)
            loop.call_soon_threadsafe(q.put_nowait, None) # Sentinel
        except Exception as e:
            loop.call_soon_threadsafe(q.put_nowait, {"event": "error", "error": str(e)})
            loop.call_soon_threadsafe(q.put_nowait, None)

    # Start the blocking generator in a separate thread
    threading.Thread(target=producer, daemon=True).start()

    # Consume the queue asynchronously
    while True:
        item = await q.get()
        if item is None:
            break
        yield item

# 2. 用户登录管理 (User Login Management)
# Chainlit looks for this callback to enable authentication
# @cl.password_auth_callback
# def auth_callback(username, password):
#     # Simple hardcoded credentials for demo
#     # In production, check against a database or auth provider
#     # You can also use environment variables
#     import os
#     valid_username = os.environ.get("APP_USER", "admin")
#     valid_password = os.environ.get("APP_PASSWORD", "admin")
    
#     if username == valid_username and password == valid_password:
#         return cl.User(identifier=username)
#     return None

async def heartbeat(msg: cl.Message):
    while True:
        await asyncio.sleep(5)
        await msg.update(content="⏳ 分析中，请稍候…")


# 3. Chainlit 主逻辑 (Main Logic)
@cl.on_chat_start
async def start():
    # Welcome message
    await cl.Message(content='''
    ### 📌 使用方式

**输入 Jira 号 + 可选上传日志文件**

- 仅分析你上传的日志文件（支持 `.log` 或 `.txt` 格式）  
- 如果不上传日志，也可以只传 Jira 号，我会基于 Jira 信息进行分析  
- 不会下载 Jira 中的附件日志  

---

⏳ 日志分析可能需要 **1–5 分钟**，请耐心等待。  
准备好后，直接发送 **Jira 号（可选附日志）** 即可开始。

''').send()

#写一个流式输出的函数，入参是message或者step组件以及要显示的字符串和单字输出的速度，函数体实现单字输出的效果
async def stream_output(msg: cl.Message, content: str, speed: float = 0.015):
    for char in content:
        await msg.stream_token(char)
        await asyncio.sleep(speed)


@cl.on_message
async def main(message: cl.Message):
    # 3. 支持泡泡内容的清除 (Clear Chat Support)
    # The "New Chat" button in the UI already supports clearing the context.
    # However, if we want to ensure we are starting fresh or managing specific state:
    
    # Run the processing function
    # Strategy: 
    # 1. Create a "Status Message" to hold the steps. This ensures it stays at the top.
    # 2. Attach steps to this Status Message.
    # 3. Send the Final Message after processing is done.
    
    status_msg = cl.Message(content="🔎 **Analysis in progress...**")
    await status_msg.send()
    steps = []
    current_step = None
    # hb_task = asyncio.create_task(heartbeat(status_msg))
    async for response in process_input(message.content, message.elements):
        if "event" in response:
            if response.get("event") != "content":
                event = response["event"]
                if not current_step:
                    current_step = cl.Step(
                        name=event,
                        parent_id=status_msg.id,
                        default_open=True
                    )
                    await current_step.send()
                    steps.append(current_step)
                    await stream_output(
                        current_step,
                        response.get("body", "")
                    )
                    await current_step.update()
                # event 变了 → 新建 step（不删除旧的）
                elif current_step.name != event:
                    await current_step.remove()
                    current_step = cl.Step(
                        name=event,
                        parent_id=status_msg.id,
                        default_open=True
                    )
                    steps.append(current_step)
                    await current_step.send()

                    await stream_output(
                        current_step,
                        response.get("body", "")
                    )
                    await current_step.update()
            else:
                # Close the step if it exists
                for step in steps:
                    await step.remove()

                # Update the status message to show completion
                status_msg.content = "✅ **Analysis Process**"
                await status_msg.update()
                
                # Create and send the final message
                final_msg = cl.Message(content="")
                await final_msg.send()
                
                # Stream the final content
                await stream_output(final_msg, response.get("body", ""))
                await final_msg.update()
        else:
            print(response)
    # hb_task.cancel()

