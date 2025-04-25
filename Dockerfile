FROM python:3.12-slim-bookworm

# 安装基础包
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    pandoc \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# 复制依赖文件
COPY ./requirements.txt /code/requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 复制测试 PDF 并执行转换来预下载模型
COPY ./test.pdf /code/test.pdf
RUN python -c "from docling.document_converter import DocumentConverter; \
    from docling.datamodel.base_models import InputFormat; \
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions; \
    from docling.document_converter import PdfFormatOption; \
    pipeline_options = PdfPipelineOptions(); \
    ocr_options = RapidOcrOptions(force_full_page_ocr=True); \
    pipeline_options.ocr_options = ocr_options; \
    format_option = PdfFormatOption(pipeline_options=pipeline_options); \
    converter = DocumentConverter(format_options={InputFormat.PDF: format_option}); \
    doc = converter.convert('test.pdf').document; \
    doc.export_to_html()" && \
    rm test.pdf

# 复制应用代码
COPY ./main.py /code/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--timeout-keep-alive", "200"]