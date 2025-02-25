from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.responses import FileResponse
from tempfile import mkdtemp
from pdf2docx import Converter
import asyncio
import pypandoc
import logging
import os
import subprocess
import sys
import signal
import multiprocessing as mp

app = FastAPI()

logging.basicConfig(level=logging.INFO)

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "hello, world!"

@app.get("/ping", response_class=PlainTextResponse)
async def pong():
    return "pong"

@app.post("/convert")
async def convert(from_format: str = Form(...), to_format: str = Form(...), file: UploadFile = File(None), content: str = Form(None)):
    print("收到请求 from_format: ", from_format, " to_format: ", to_format , " file: ", file, " content: ", content)

    if to_format == "pdf":
        raise HTTPException(status_code=400, detail="Conversion to pdf is not supported")
    if file is None and content is None:
        raise HTTPException(status_code=400, detail="Either a file or content must be provided.")
    
    tmpdir = mkdtemp()
    input_path = os.path.join(tmpdir, f'input.{from_format}')
    intermediate_path = os.path.join(tmpdir, f'intermediate.docx')
    output_path = os.path.join(tmpdir, f'output.{to_format}')
        
    try:
        await save_uploaded_file(file, content, input_path)
        if from_format == "pdf":
            await convert_pdf_to_docx(input_path, intermediate_path)
            logging.info("PDF转换成功")
            if to_format == "docx":
                final_path = intermediate_path
            else:
                await convert_with_pandoc(from_format, intermediate_path, to_format, output_path)
                logging.info("Pandoc转换成功")
                final_path = output_path
        else:
            await convert_with_pandoc(from_format, input_path, to_format, output_path)
            logging.info("Pandoc转换成功")
            final_path = output_path

        response = FileResponse(path=final_path, filename=f'converted.{to_format}', media_type='application/octet-stream')
        asyncio.create_task(delete_files_async([input_path, intermediate_path, output_path], 60))  # Delay in seconds
        return response

    except Exception as e:
        asyncio.create_task(delete_files_async([input_path, intermediate_path, output_path], 0))  # Immediate cleanup
        logging.error(f"Error during conversion: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
async def save_uploaded_file(file, content, path):
    if file:
        content = await file.read()
    elif content:
        content = content.encode()
    
    with open(path, 'wb') as f:
        f.write(content)

async def convert_pdf_to_docx(input_path, output_path):
    # 设置超时时间（秒）
    timeout = 60
    
    try:
        # 创建一个Python脚本来执行转换
        script = f"""
import sys
import os
import signal
from pdf2docx import Converter
import multiprocessing as mp
import logging

# 设置进程组，便于后续终止所有子进程
os.setpgrp()

# 添加信号处理器，确保优雅关闭
def handle_term(signum, frame):
    if 'cv' in globals() and cv:
        try:
            cv.close()
        except:
            pass
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_term)

try:
    cv = Converter('{input_path}')
    cv.convert('{output_path}', multi_processing=True)
    cv.close()
    sys.exit(0)
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    if 'cv' in locals() and cv:
        try:
            cv.close()
        except:
            pass
    sys.exit(1)
"""
        # 使用subprocess运行脚本，设置超时
        process = None
        try:
            # 使用Popen启动进程
            process = subprocess.Popen(
                [sys.executable, '-c', script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid
            )
            
            # 等待进程完成，带有超时
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                if process.returncode != 0:
                    raise Exception(f"PDF转换失败: {stderr}")
            except subprocess.TimeoutExpired:
                # 终止整个进程组
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    # 给进程一点时间来清理
                    process.wait(timeout=1)
                except:
                    # 如果进程没有及时终止，强制终止
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except:
                        pass 
                raise Exception(f"PDF转换超时，超过了{timeout}秒的限制")
                
        except Exception as e:
            if not isinstance(e, subprocess.TimeoutExpired):
                # 确保进程被终止
                if process and process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except:
                        pass
                raise Exception(f"PDF转换失败: {e}")
            else:
                raise
    except Exception as e:
        logging.error(f"PDF转换出错: {e}")
        raise

async def convert_with_pandoc(from_format, input_path, to_format, output_path):
    if from_format == 'txt' and to_format == 'html':
        with open(input_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        text = ''.join(line.strip() + '  \n' for line in lines)
        output = pypandoc.convert_text(text, 'html', format='markdown')
        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(output)
    else:
        pdoc_args = ["--embed-resources", "--request-header", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"]
        pypandoc.convert_file(input_path, to_format, outputfile=output_path, extra_args=pdoc_args)

async def delete_files_async(file_paths, delay):
    await asyncio.sleep(delay)
    for path in file_paths:
        if os.path.exists(path):
            os.remove(path)
