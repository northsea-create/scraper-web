import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import logging
from flask import Flask, render_template_string, request, jsonify, send_from_directory
import threading
import time
import datetime

# 配置日志 - 增加详细程度
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 全局变量
default_download_folder = "downloads"
last_run_time = None
running = False
debug_info = []  # 用于存储调试信息
progress = {"total": 0, "current": 0, "filename": "", "percentage": 0}  # 添加进度信息

# HTML模板 (修改后)
html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>PDF爬虫</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f4f4f4;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background-color: #fff;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-top: 10px;
        }
        button:hover {
            background-color: #45a049;
        }
        button:disabled {
            background-color: #cccccc;
            cursor: not-allowed;
        }
        input[type="text"], input[type="number"], select {
            width: 100%;
            padding: 8px;
            margin: 6px 0;
            display: inline-block;
            border: 1px solid #ccc;
            border-radius: 4px;
            box-sizing: border-box;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            font-weight: bold;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .status {
            margin: 20px 0;
            padding: 10px;
            border-radius: 4px;
        }
        .running {
            background-color: #fff3cd;
            color: #856404;
        }
        .success {
            background-color: #d4edda;
            color: #155724;
        }
        .debug-info {
            margin-top: 30px;
            padding: 10px;
            background-color: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 4px;
            max-height: 300px;
            overflow-y: auto;
        }
        .debug-item {
            margin-bottom: 5px;
            font-family: monospace;
        }
        .progress-container {
            width: 100%;
            background-color: #f1f1f1;
            border-radius: 4px;
            margin: 10px 0;
        }
        .progress-bar {
            height: 20px;
            background-color: #4CAF50;
            border-radius: 4px;
            text-align: center;
            color: white;
            line-height: 20px;
            transition: width 0.3s;
        }
        .progress-info {
            margin: 5px 0;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>PDF爬虫</h1>
        
        <div id="status" class="status">
            {% if running %}
                <div class="running">爬虫正在运行中...</div>
            {% elif last_run %}
                <div class="success">上次运行时间: {{ last_run }}</div>
            {% else %}
                <div>爬虫尚未运行</div>
            {% endif %}
        </div>
        
        <form id="crawlForm">
            <div class="form-group">
                <label for="baseUrl">抓取网站:</label>
                <input type="text" id="baseUrl" name="baseUrl" placeholder="输入要抓取的网站URL" required>
            </div>
            
            <div class="form-group">
                <label for="downloadPath">下载路径:</label>
                <input type="text" id="downloadPath" name="downloadPath" value="{{ default_path }}" placeholder="输入保存文件的路径">
            </div>
            
            <div class="form-group">
                <label>时间范围:</label>
                <div style="display: flex; gap: 10px;">
                    <div style="flex: 1;">
                        <label for="startYear">开始年份:</label>
                        <input type="number" id="startYear" name="startYear" min="2000" max="2050" value="{{ current_year-1 }}">
                    </div>
                    <div style="flex: 1;">
                        <label for="endYear">结束年份:</label>
                        <input type="number" id="endYear" name="endYear" min="2000" max="2050" value="{{ current_year }}">
                    </div>
                </div>
            </div>
            
            <button type="button" id="startBtn" onclick="startCrawl()" {% if running %}disabled{% endif %}>
                开始爬取
            </button>
        </form>
        
        <div id="progressSection" style="display: none;">
            <h3>下载进度</h3>
            <div class="progress-info">
                <span id="progressFile">准备中...</span>
            </div>
            <div class="progress-container">
                <div id="progressBar" class="progress-bar" style="width: 0%">0%</div>
            </div>
            <div class="progress-info">
                <span id="progressCount">0 / 0</span> 文件已完成
            </div>
        </div>
        
        <h2>已下载文件 (<span id="fileCount">{{ files|length }}</span>)</h2>
        <table>
            <thead>
                <tr>
                    <th>文件名</th>
                    <th>下载时间</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody id="fileList">
                {% for file in files %}
                <tr>
                    <td>{{ file }}</td>
                    <td>{{ last_modified(file) }}</td>
                    <td><a href="/downloads/{{ file }}" download>下载</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        
        <div class="debug-info">
            <h3>调试信息</h3>
            <div id="debugItems">
                {% for info in debug_info %}
                <div class="debug-item">{{ info }}</div>
                {% endfor %}
            </div>
        </div>
    </div>

    <script>
        function startCrawl() {
            const baseUrl = document.getElementById('baseUrl').value;
            const downloadPath = document.getElementById('downloadPath').value;
            const startYear = document.getElementById('startYear').value;
            const endYear = document.getElementById('endYear').value;
            
            if (!baseUrl) {
                alert('请输入要抓取的网站URL');
                return;
            }
            
            document.getElementById('startBtn').disabled = true;
            document.getElementById('status').innerHTML = '<div class="running">爬虫正在运行中...</div>';
            document.getElementById('progressSection').style.display = 'block';
            document.getElementById('progressBar').style.width = '0%';
            document.getElementById('progressBar').textContent = '0%';
            document.getElementById('progressFile').textContent = '准备中...';
            document.getElementById('progressCount').textContent = '0 / 0';
            
            fetch('/start_crawl', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    baseUrl: baseUrl,
                    downloadPath: downloadPath,
                    startYear: startYear,
                    endYear: endYear
                })
            })
            .then(response => response.json())
            .then(data => {
                console.log(data);
                // 开始定期检查状态和进度
                checkStatusAndProgress();
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('startBtn').disabled = false;
            });
        }
        
        function checkStatusAndProgress() {
            fetch('/status')
            .then(response => response.json())
            .then(data => {
                // 更新进度条
                if (data.progress) {
                    const progressBar = document.getElementById('progressBar');
                    progressBar.style.width = data.progress.percentage + '%';
                    progressBar.textContent = data.progress.percentage + '%';
                    
                    document.getElementById('progressFile').textContent = 
                        data.progress.filename ? '当前下载: ' + data.progress.filename : '准备中...';
                    
                    document.getElementById('progressCount').textContent = 
                        data.progress.current + ' / ' + data.progress.total;
                }
                
                // 更新调试信息
                if (data.debug_info && data.debug_info.length > 0) {
                    const debugItems = document.getElementById('debugItems');
                    // 只添加新的调试信息
                    const currentItems = debugItems.querySelectorAll('.debug-item');
                    const currentCount = currentItems.length;
                    
                    if (data.debug_info.length > currentCount) {
                        for (let i = currentCount; i < data.debug_info.length; i++) {
                            const div = document.createElement('div');
                            div.className = 'debug-item';
                            div.textContent = data.debug_info[i];
                            debugItems.appendChild(div);
                        }
                        // 滚动到底部
                        const debugInfo = document.querySelector('.debug-info');
                        debugInfo.scrollTop = debugInfo.scrollHeight;
                    }
                }
                
                if (data.running) {
                    // 如果仍在运行，继续检查
                    setTimeout(checkStatusAndProgress, 1000);
                } else {
                    // 如果已完成，刷新页面
                    window.location.reload();
                }
            })
            .catch(error => {
                console.error('Error:', error);
                setTimeout(checkStatusAndProgress, 2000);
            });
        }
    </script>
</body>
</html>
"""

# 确保下载目录存在
if not os.path.exists(default_download_folder):
    os.makedirs(default_download_folder)

def add_debug_info(message):
    """添加调试信息"""
    global debug_info
    debug_info.append(message)
    if len(debug_info) > 100:  # 增加限制条目数
        debug_info = debug_info[-100:]
    logger.debug(message)

def extract_year_from_text(text):
    """从文本中提取年份"""
    # 匹配四位数年份，如"2025年"或"2025-"
    year_match = re.search(r'(20\d{2})[年\-]', text)
    if year_match:
        return year_match.group(1)
    return None

def extract_month_from_text(text):
    """从文本中提取月份"""
    # 匹配月份，如"3月"或"03"
    month_match = re.search(r'(\d{1,2})[月\-]', text)
    if month_match:
        return month_match.group(1).zfill(2)  # 补齐成两位数
    return None

def extract_name_from_text(text):
    """从文本中提取有意义的名称"""
    # 尝试匹配"信息价"、"造价信息"等关键词
    name_match = re.search(r'(造价[信息]*|信息价|定额|指数|参考价|市场价|建设工程)', text)
    if name_match:
        return name_match.group(1)
    return None

def generate_file_name(url, original_name):
    """根据URL和原始文件名生成新的文件名"""
    # 从URL的路径部分提取文本
    path = urlparse(url).path
    path_text = path.replace('/', ' ').strip()
    
    # 从URL和文件名中提取年份和月份
    year = extract_year_from_text(path_text) or extract_year_from_text(original_name)
    month = extract_month_from_text(path_text) or extract_month_from_text(original_name)
    name_part = extract_name_from_text(path_text) or extract_name_from_text(original_name) or "信息价"
    
    # 构建新文件名
    if year and month:
        new_name = f"{year}年{month}月{name_part}.pdf"
    elif year:
        new_name = f"{year}年{name_part}.pdf"
    else:
        # 如果无法提取时间信息，使用原始文件名
        new_name = original_name
        
    return new_name

def is_in_year_range(url, text, start_year, end_year):
    """检查URL或文本中的年份是否在指定范围内"""
    if not start_year or not end_year:
        return True  # 如果未指定范围，默认包含所有

    # 从URL和文本中提取年份
    year_text = url + " " + text
    year_match = re.search(r'(20\d{2})', year_text)
    
    if year_match:
        year = int(year_match.group(1))
        return int(start_year) <= year <= int(end_year)
    
    # 如果无法提取年份，默认包含
    return True

def download_pdf(url, folder, update_progress=None):
    """下载PDF文件并保存到指定文件夹"""
    try:
        add_debug_info(f"尝试下载: {url}")
        
        # 发送请求获取PDF内容
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/pdf,*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive'
        }
        
        response = requests.get(url, stream=True, headers=headers, timeout=30)
        
        # 检查是否为PDF
        content_type = response.headers.get('Content-Type', '')
        add_debug_info(f"Content-Type: {content_type}")
        
        if response.status_code == 200:
            # 从URL中提取文件名
            original_file_name = url.split('/')[-1]
            
            # 确保文件名以.pdf结尾
            if not original_file_name.lower().endswith('.pdf'):
                if 'application/pdf' in content_type:
                    original_file_name += '.pdf'
                else:
                    add_debug_info(f"忽略非PDF文件: {url}")
                    if update_progress:
                        update_progress(skipped=True)
                    return None
            
            # 生成新文件名
            file_name = generate_file_name(url, original_file_name)
            add_debug_info(f"文件将被保存为: {file_name}")
            
            file_path = os.path.join(folder, file_name)
            
            # 检查内容长度
            content_length = int(response.headers.get('Content-Length', 0))
            add_debug_info(f"内容长度: {content_length} 字节")
            
            if content_length < 1000:  # 如果文件太小，可能不是有效的PDF
                add_debug_info(f"文件太小，可能不是有效的PDF: {content_length} 字节")
                
                # 检查内容的前几个字节是否是PDF标识
                first_bytes = next(response.iter_content(chunk_size=10), b'')
                if not first_bytes.startswith(b'%PDF'):
                    add_debug_info(f"内容不是以PDF标识开头")
                    if update_progress:
                        update_progress(skipped=True)
                    return None
            
            # 保存文件
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            add_debug_info(f"成功下载: {file_name}")
            if update_progress:
                update_progress(success=True, filename=file_name)
            return file_name
        else:
            add_debug_info(f"下载失败, 状态码: {response.status_code}, URL: {url}")
            if update_progress:
                update_progress(skipped=True)
            return None
    except Exception as e:
        add_debug_info(f"下载过程中出错: {str(e)}, URL: {url}")
        if update_progress:
            update_progress(skipped=True)
        return None

def get_pdf_links(url, start_year=None, end_year=None, depth=0, max_depth=3, visited=None):
    """获取页面上的PDF链接，支持递归和循环检测"""
    if visited is None:
        visited = set()
    
    if url in visited or depth > max_depth:
        return []
    
    visited.add(url)
    add_debug_info(f"正在检查页面 (深度 {depth}): {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        add_debug_info(f"HTTP状态码: {response.status_code}")
        
        if response.status_code == 200:
            # 尝试检测编码
            if 'content-type' in response.headers:
                content_type = response.headers['content-type']
                add_debug_info(f"Content-Type: {content_type}")
                
                # 尝试解析为不同的编码
                try:
                    html_content = response.content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        html_content = response.content.decode('gbk')
                    except UnicodeDecodeError:
                        html_content = response.content.decode('gb2312', errors='ignore')
            else:
                html_content = response.text
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 提取页面标题
            title = soup.title.string if soup.title else "无标题"
            add_debug_info(f"页面标题: {title}")
            
            # 查找所有链接
            links = soup.find_all('a')
            add_debug_info(f"找到链接数量: {len(links)}")
            
            pdf_links = []
            potential_subpages = []
            
            # 优先搜索直接的PDF链接
            for link in links:
                href = link.get('href')
                if not href:
                    continue
                
                # 转为完整URL
                full_url = urljoin(url, href)
                
                # 获取链接文本
                link_text = link.text.strip() if link.text else ""
                
                # 检查链接是否以.pdf结尾
                if href.lower().endswith('.pdf'):
                    # 检查是否在年份范围内
                    if is_in_year_range(full_url, link_text, start_year, end_year):
                        add_debug_info(f"找到PDF链接: {full_url}")
                        pdf_links.append(full_url)
                    else:
                        add_debug_info(f"PDF链接不在指定年份范围内，已忽略: {full_url}")
                
                # 收集可能包含PDF的页面链接
                if ('造价信息' in link_text or '造价' in link_text or '信息价' in link_text 
                    or '建设工程' in link_text or '定额' in link_text):
                    potential_subpages.append((full_url, link_text))
                    add_debug_info(f"找到潜在内容页面: {link_text} -> {full_url}")
            
            # 如果没有直接找到PDF但有潜在子页面，递归检查
            if potential_subpages and depth < max_depth:
                for subpage_url, subpage_text in potential_subpages:
                    if subpage_url not in visited:
                        add_debug_info(f"递归检查: {subpage_text} -> {subpage_url}")
                        sub_pdf_links = get_pdf_links(subpage_url, start_year, end_year, depth + 1, max_depth, visited)
                        pdf_links.extend(sub_pdf_links)
            
            return pdf_links
        else:
            add_debug_info(f"获取页面失败, 状态码: {response.status_code}, URL: {url}")
            return []
    except Exception as e:
        add_debug_info(f"获取PDF链接过程中出错: {str(e)}, URL: {url}")
        return []

def crawl_pdfs(base_url, download_folder, start_year=None, end_year=None):
    """爬取网站上的所有PDF"""
    global running, last_run_time, debug_info, progress
    running = True
    debug_info = []  # 重置调试信息
    progress = {"total": 0, "current": 0, "filename": "", "percentage": 0}  # 重置进度
    
    try:
        add_debug_info(f"开始爬取PDF，网站: {base_url}")
        add_debug_info(f"下载路径: {download_folder}")
        add_debug_info(f"年份范围: {start_year} - {end_year}")
        
        # 确保下载目录存在
        if not os.path.exists(download_folder):
            os.makedirs(download_folder)
            add_debug_info(f"创建下载目录: {download_folder}")
        
        # 获取所有PDF链接
        pdf_links = get_pdf_links(base_url, start_year, end_year)
        add_debug_info(f"找到 {len(pdf_links)} 个PDF链接")
        
        # 设置进度信息
        progress["total"] = len(pdf_links)
        progress["current"] = 0
        
        # 打印所有找到的链接
        for i, link in enumerate(pdf_links):
            add_debug_info(f"链接 {i+1}: {link}")
        
        # 定义进度更新函数
        def update_progress(success=False, skipped=False, filename=""):
            global progress
            if success or skipped:
                progress["current"] += 1
            
            if success and filename:
                progress["filename"] = filename
            
            if progress["total"] > 0:
                progress["percentage"] = int((progress["current"] / progress["total"]) * 100)
            else:
                progress["percentage"] = 100
        
        # 下载所有PDF
        downloaded_files = []
        for link in pdf_links:
            progress["filename"] = link.split('/')[-1]  # 设置当前正在下载的文件名
            filename = download_pdf(link, download_folder, update_progress)
            if filename:
                downloaded_files.append(filename)
        
        add_debug_info(f"爬取完成，成功下载 {len(downloaded_files)} 个文件")
        last_run_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        progress["filename"] = "完成"
        progress["percentage"] = 100
        
        return downloaded_files
    except Exception as e:
        add_debug_info(f"爬取过程中出错: {str(e)}")
        return []
    finally:
        running = False

# 获取文件的最后修改时间
def get_last_modified(filename):
    file_path = os.path.join(default_download_folder, filename)
    if os.path.exists(file_path):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(file_path)))
    return "未知"

# Web服务路由
@app.route('/')
def index():
    """网站首页"""
    # 获取下载目录中的文件列表
    files = os.listdir(default_download_folder) if os.path.exists(default_download_folder) else []
    # 按修改时间排序文件
    files.sort(key=lambda x: os.path.getmtime(os.path.join(default_download_folder, x)), reverse=True)
    
    # 获取当前年份
    current_year = datetime.datetime.now().year
    
    return render_template_string(html_template, 
                                files=files, 
                                last_run=last_run_time, 
                                running=running,
                                debug_info=debug_info,
                                last_modified=get_last_modified,
                                default_path=default_download_folder,
                                current_year=current_year)

@app.route('/start_crawl', methods=['POST'])
def start_crawl():
    """启动爬虫"""
    global running
    if running:
        return jsonify({"status": "error", "message": "爬虫正在运行中"})
    
    # 获取参数
    data = request.json
    base_url = data.get('baseUrl', '')
    download_path = data.get('downloadPath', default_download_folder)
    start_year = data.get('startYear', '')
    end_year = data.get('endYear', '')
    
    if not base_url:
        return jsonify({"status": "error", "message": "请提供有效的网站URL"})
    
    # 如果下载路径为空，使用默认路径
    if not download_path:
        download_path = default_download_folder
    
    # 在新线程中运行爬虫
    threading.Thread(target=crawl_pdfs, args=(base_url, download_path, start_year, end_year)).start()
    return jsonify({"status": "success", "message": "爬虫已启动"})

@app.route('/status')
def status():
    """返回爬虫状态"""
    files = os.listdir(default_download_folder) if os.path.exists(default_download_folder) else []
    return jsonify({
        "running": running,
        "last_run": last_run_time,
        "file_count": len(files),
        "debug_info": debug_info,
        "progress": progress
    })

# 添加静态文件服务
@app.route('/downloads/<path:filename>')
def download_file(filename):
    return send_from_directory(default_download_folder, filename, as_attachment=True)

if __name__ == "__main__":
    # 程序入口点
    app.run(host='0.0.0.0', port=5000, debug=True)
