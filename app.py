import chainlit as cl
import asyncio
import threading
import re
import time
from urllib.parse import urlparse, parse_qs
from typing import Dict, Optional
from test_client import analyze_logs_stream
from utils.logger import chainlit_log
from utils.config import load_config
from utils.jira_client import MyJira
from utils.mysql_client import MySQLClient



config = load_config()
chainlit_log(f"加载配置成功 load_config:{load_config}")
myjira = MyJira(config.jira_server, config.jira_username, config.jira_password)
mysql_client = MySQLClient(
    host=config.mysql_host,
    port=config.mysql_port,
    user=config.mysql_user,
    password=config.mysql_password,
    database=config.mysql_database,
    table=config.mysql_table,
    analysis_table=config.mysql_analysis_table,
)
mysql_client.init_feedback_storage(config.mysql_database, config.mysql_table)
mysql_client.init_analysis_storage(config.mysql_database, config.mysql_analysis_table)
chainlit_log(f"数据库配置成功 连接:{config.mysql_database}.{config.mysql_table}/{config.mysql_analysis_table}")
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
            chainlit_log("退出主循环")
            break
        yield item


def extract_key_from_url_request(url: str) -> Optional[str]:
    """从 URL 查询参数中提取 key 值。"""
    parsed_url = urlparse(url)
    params = parse_qs(parsed_url.query)
    if params.get("key"):
        return params["key"][0]
    return None


def extract_key_from_session_env() -> Optional[str]:
    """从会话环境或请求上下文中提取 key 参数。"""
    context = getattr(cl, "context", None)
    session = getattr(context, "session", None)
    environ = getattr(session, "environ", None) or {}

    referer = environ.get("HTTP_REFERER", "")
    chainlit_log(f"referer:{referer}")
    if referer:
        referer_key = extract_key_from_url_request(referer)
        if referer_key:
            return referer_key
    return None


def get_client_ip() -> Optional[str]:
    context = getattr(cl, "context", None)
    session = getattr(context, "session", None)
    environ = getattr(session, "environ", None) or {}
    forwarded = environ.get("HTTP_X_FORWARDED_FOR", "")
    chainlit_log(f"forwarded:{forwarded}")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = environ.get("HTTP_X_REAL_IP", "")
    chainlit_log(f"real_ip:{real_ip}")
    if real_ip:
        return real_ip
    remote_addr = environ.get("REMOTE_ADDR")
    chainlit_log(f"remote_addr:{remote_addr}")
    return remote_addr


async def run_analysis(text: str, elements: Optional[list]) -> None:
    """执行分析流程并输出步骤与最终结果。"""
    status_msg = cl.Message(content="🔎 **Analysis in progress...**")
    # 清掉之前的组件
    prev_feedback_element = cl.user_session.get("feedback_element")
    if prev_feedback_element:
        try:
            await prev_feedback_element.remove()
        except Exception as exc:
            chainlit_log(f"remove feedback_element error:{exc}")
    match = re.search(r"[A-Za-z]+-\d+", text or "")
    if match:
        input_text = match.group(0)
    else:
        input_text = ""
    chainlit_log(f"message.content:{text}")
    await status_msg.send()
    cl.user_session.set("last_issue_key", text)
    steps = []
    current_step = None
    async for response in process_input(text, elements):
        chainlit_log(f"response:{response}")
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
                # for step in steps:
                #     await step.remove()

                # Update the status message to show completion
                status_msg.content = "✅ **Analysis Process**"
                await status_msg.update()

                # Create and send the final message
                final_msg = cl.Message(content="")
                

                # Stream the final content
                result_body = response.get("body", "")
                cl.user_session.set("last_analysis_result", result_body)
                await stream_output(final_msg, result_body)
                await final_msg.send()
                try:
                    mysql_client.insert_analysis_log(
                        ip=get_client_ip(),
                        input_text=text,
                        result_body=result_body,
                    )
                except Exception as exc:
                    chainlit_log(f"insert_analysis_log error:{exc}")

                invalid_msg = "No files provided for log analysis."
                # if result_body != invalid_msg:
                if input_text:
                    feedback_element = cl.CustomElement(
                        name="FeedbackPanel",
                        props={
                            "feedbackState": None,
                            "autoCommentState": None,
                            "last_issue_key": text,
                        },
                    )
                    final_msg.elements = [feedback_element]

                    cl.user_session.set("feedback_element", feedback_element)
                    cl.user_session.set("feedback_state", None)
                    cl.user_session.set("auto_comment_state", None)
                    cl.user_session.set("suggestion_state", None)
                    cl.user_session.set("auto_comment_pending", False)

                await final_msg.update()

        else:
            chainlit_log(response)

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
    """定时刷新状态消息提示仍在分析。"""
    while True:
        await asyncio.sleep(5)
        await msg.update(content="⏳ 分析中，请稍候…")


# 3. Chainlit 主逻辑 (Main Logic)
@cl.on_chat_start
async def start():
    """聊天启动时发送说明并尝试自动触发分析。"""
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
    auto_key = extract_key_from_session_env()
    if auto_key:
        await run_analysis(auto_key, None)

#写一个流式输出的函数，入参是message或者step组件以及要显示的字符串和单字输出的速度，函数体实现单字输出的效果
async def stream_output(msg: cl.Message, content: str, speed: float = 0.015):
    """按指定速度逐字流式输出内容。"""
    for char in content:
        await msg.stream_token(char)
        await asyncio.sleep(speed)


@cl.on_message
async def main(message: cl.Message):
    """处理用户消息并启动分析。"""
    # 3. 支持泡泡内容的清除 (Clear Chat Support)
    # The "New Chat" button in the UI already supports clearing the context.
    # However, if we want to ensure we are starting fresh or managing specific state:
    
    # Run the processing function
    # Strategy: 
    # 1. Create a "Status Message" to hold the steps. This ensures it stays at the top.
    # 2. Attach steps to this Status Message.
    # 3. Send the Final Message after processing is done.
    
    await run_analysis(message.content, message.elements)


def add_comment_to_jira(issue_key: str, comment_body: str) -> None:

    chainlit_log(f"issue_key:{issue_key}")
    jira_comment_header = '''
    ⚠️ AI智能分析(For reference only) 有任何意见和建议可随时联系 nan.li或 lingzhi.bi
'''
    web_link = f'''\n🔗 Reference:
不便上传至 Jira 的日志，可通过以下地址在线分析：
http://10.18.11.98:5000/
如对本次自动分析结果存在疑问、发现异常情况或有优化建议，欢迎通过以下地址提交反馈：
http://10.18.11.98:8053/?page=feedback'''
    comment_body = jira_comment_header + comment_body +  web_link
    myjira.addComments(issue_key, comment_body)
    return None


@cl.action_callback("feedback")
async def handle_feedback(action: cl.Action):
    payload = getattr(action, "payload", {}) or {}
    feedback_value = payload.get("value", "")
    issue_key = cl.user_session.get("last_issue_key")
    analysis_result = cl.user_session.get("last_analysis_result")
    suggestion = payload.get("suggestion")
    client_ip = get_client_ip()
    extra = {
        "source": {
            "issue_key": issue_key,
            "analysis_result": analysis_result,
        }
    }
    try:
        existing = mysql_client.get_feedback_by_analysis_result(issue_key, analysis_result)
        if existing:
            stored_feedback = existing.get("feedback")
            stored_suggestion = existing.get("feedback_suggestion")
            normalized_feedback = feedback_value
            if stored_feedback != normalized_feedback:
                mysql_client.update_feedback(
                    feedback_id=existing.get("feedback_id"),
                    feedback_value=feedback_value,
                    suggestion=stored_suggestion,
                    extra=extra,
                    ip=client_ip,
                )
                chainlit_log(f"更新数据库：feedback_value:{feedback_value}, extra:{extra}")
        else:
            mysql_client.insert_feedback(
                feedback_value=feedback_value,
                suggestion=suggestion,
                extra=extra,
                ip=client_ip,
            )
            chainlit_log(f"插入数据库：feedback_value{feedback_value}, suggestion:{suggestion}, extra:{extra}")
    except Exception as exc:
        chainlit_log(f"insert_feedback error:{exc}")
    chainlit_log(f"set feedbackState:{feedback_value}")
    cl.user_session.set("feedback_state", feedback_value)
    await refresh_feedback_message()


@cl.action_callback("suggestion_submit")
async def handle_suggestion_submit(action: cl.Action):
    payload = getattr(action, "payload", {}) or {}
    suggestion = payload.get("suggestion")
    if not suggestion:
        return
    feedback_value = cl.user_session.get("feedback_state")
    issue_key = cl.user_session.get("last_issue_key")
    analysis_result = cl.user_session.get("last_analysis_result")
    client_ip = get_client_ip()
    extra = {
        "source": {
            "issue_key": issue_key,
            "analysis_result": analysis_result,
        }
    }
    try:
        existing = mysql_client.get_feedback_by_analysis_result(issue_key, analysis_result)
        if existing:
            stored_feedback = existing.get("feedback")
            stored_suggestion = existing.get("feedback_suggestion")
            if stored_suggestion != suggestion:
                mysql_client.update_feedback(
                    feedback_id=existing.get("feedback_id"),
                    feedback_value=stored_feedback,
                    suggestion=suggestion,
                    extra=extra,
                    ip=client_ip,
                )
                chainlit_log(f"更新建议到数据库：suggestion:{suggestion}, extra:{extra}")
                cl.user_session.set("suggestion_state", "已提交")
        else:
            mysql_client.insert_feedback(
                feedback_value=feedback_value,
                suggestion=suggestion,
                extra=extra,
                ip=client_ip,
            )
            chainlit_log(f"插入建议到数据库：feedback_value:{feedback_value}, suggestion:{suggestion}, extra:{extra}")
            cl.user_session.set("suggestion_state", "已提交")
    except Exception as exc:
        chainlit_log(f"suggestion_submit error:{exc}")
    else:
        await refresh_feedback_message()


@cl.action_callback("auto_comment")
async def handle_auto_comment(action: cl.Action):
    issue_key = cl.user_session.get("last_issue_key")
    analysis_result = cl.user_session.get("last_analysis_result")

    if not issue_key:
        cl.user_session.set("auto_comment_state", "❌ 未找到 Jira 号")
        await refresh_feedback_message()
        return
    if not analysis_result:
        cl.user_session.set("auto_comment_state", "❌ 未找到分析结果")
        await refresh_feedback_message()
        return
    try:
        existing = myjira.getAiCommentTimeWithSql(f"key = {issue_key}")
        pending = cl.user_session.get("auto_comment_pending")
        if existing:
            if not pending:
                cl.user_session.set("auto_comment_pending", True)
                cl.user_session.set("auto_comment_state", f"⚠️ {issue_key} 已有 AI智能分析 ，需要再次添加，请再点击一次")
                chainlit_log(f"⚠️ {issue_key} 已有评论，再点一次确认")
                await refresh_feedback_message()
                return
        add_comment_to_jira(issue_key, analysis_result)
        try:
            updated = mysql_client.update_analysis_log_add_comment(
                input_text=issue_key,
                result_body=analysis_result,
            )
            chainlit_log(f"update_analysis_log_add_comment:{updated}")
        except Exception as exc:
            chainlit_log(f"update_analysis_log_add_comment error:{exc}")
        cl.user_session.set("auto_comment_pending", False)
        cl.user_session.set("auto_comment_state", f"✅ AI智能分析已添加到 {issue_key}")
        chainlit_log(f"✅ 已添加到 {issue_key}")
        await refresh_feedback_message()
    except Exception as exc:
        cl.user_session.set("auto_comment_pending", False)
        cl.user_session.set("auto_comment_state", f"❌ 失败：{exc}")
        await refresh_feedback_message()

async def refresh_feedback_message() -> None:
    feedback_element = cl.user_session.get("feedback_element")
    if not feedback_element:
        return
    feedback_state = cl.user_session.get("feedback_state")
    auto_comment_state = cl.user_session.get("auto_comment_state")
    suggestion_state = cl.user_session.get("suggestion_state")
    last_issue_key = cl.user_session.get("last_issue_key")
    feedback_element.props = {
        "feedbackState": feedback_state,
        "autoCommentState": auto_comment_state,
        "last_issue_key": last_issue_key,
        "suggestionState": suggestion_state,
    }
    await feedback_element.update()
