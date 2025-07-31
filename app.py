import os
import subprocess
import json
import winreg
import psutil
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)


# 自动获取 FRPS 相关路径
def find_frps_paths():
    """在 Windows 系统中查找 FRPS 相关路径"""
    paths = {
        'config': None,
        'executable': None,
        'log': None
    }

    # 1. 检查常见安装路径
    common_paths = [
        r'C:\Program Files\frp',
        r'C:\frp',
        r'C:\Program Files (x86)\frp',
        os.path.expanduser(r'~\frp')
    ]

    # 2. 检查注册表 (如果通过安装程序安装)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\frp') as key:
            install_path = winreg.QueryValueEx(key, 'InstallPath')[0]
            common_paths.insert(0, install_path)
    except WindowsError:
        pass

    # 3. 搜索可能的路径
    for path in common_paths:
        if os.path.exists(path):
            # 查找配置文件
            for config_file in ['frps.ini', 'frps.toml', 'frps.json']:
                config_path = os.path.join(path, config_file)
                if os.path.exists(config_path):
                    paths['config'] = config_path
                    break

            # 查找可执行文件
            for exe_file in ['frps.exe', 'frps']:
                exe_path = os.path.join(path, exe_file)
                if os.path.exists(exe_path):
                    paths['executable'] = exe_path
                    break

            # 设置日志路径
            log_path = os.path.join(path, 'frps.log')
            paths['log'] = log_path

            if paths['config'] and paths['executable']:
                break

    return paths


# 获取路径
FRPS_PATHS = find_frps_paths()


def is_frps_running():
    """检查 FRPS 是否正在运行 (Windows 版本)"""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in ['frps.exe', 'frps']:
            return True
    return False


def get_frps_config():
    """读取 FRPS 配置"""
    if not FRPS_PATHS['config']:
        return None

    config = {}
    try:
        with open(FRPS_PATHS['config'], 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
    except Exception as e:
        print(f"Error reading config: {e}")
        return None
    return config


def get_frps_status():
    """获取 FRPS 状态 (Windows 版本)"""
    status = {
        'running': is_frps_running(),
        'version': 'Unknown',
        'connections': 0,
        'proxies': [],
        'paths': FRPS_PATHS
    }

    if status['running'] and FRPS_PATHS['executable']:
        try:
            # 尝试获取版本信息
            result = subprocess.run(
                [FRPS_PATHS['executable'], '-v'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                status['version'] = result.stdout.strip()
        except Exception as e:
            print(f"Error getting FRPS version: {e}")

    return status


@app.route('/')
def index():
    """主页面"""
    status = get_frps_status()
    config = get_frps_config()
    return render_template('index.html', status=status, config=config)


@app.route('/api/status', methods=['GET'])
def api_status():
    """API: 获取状态"""
    return jsonify(get_frps_status())


@app.route('/api/start', methods=['POST'])
def api_start():
    """API: 启动 FRPS (Windows 版本)"""
    if is_frps_running():
        return jsonify({'success': False, 'message': 'FRPS is already running'})

    if not FRPS_PATHS['executable'] or not FRPS_PATHS['config']:
        return jsonify({'success': False, 'message': 'FRPS executable or config not found'})

    try:
        # 使用 CREATE_NO_WINDOW 避免弹出命令行窗口
        subprocess.Popen(
            [FRPS_PATHS['executable'], '-c', FRPS_PATHS['config']],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return jsonify({'success': True, 'message': 'FRPS started successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to start FRPS: {str(e)}'})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """API: 停止 FRPS (Windows 版本)"""
    if not is_frps_running():
        return jsonify({'success': False, 'message': 'FRPS is not running'})

    try:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] in ['frps.exe', 'frps']:
                proc.kill()
        return jsonify({'success': True, 'message': 'FRPS stopped successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to stop FRPS: {str(e)}'})


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """API: 获取或更新配置"""
    if request.method == 'GET':
        config = get_frps_config()
        if config is None:
            return jsonify({'success': False, 'message': 'Config file not found'})
        return jsonify({'success': True, 'config': config})
    else:
        new_config = request.json.get('config')
        if not new_config:
            return jsonify({'success': False, 'message': 'No config provided'})

        if not FRPS_PATHS['config']:
            return jsonify({'success': False, 'message': 'Config path not determined'})

        try:
            with open(FRPS_PATHS['config'], 'w', encoding='utf-8') as f:
                for key, value in new_config.items():
                    f.write(f"{key}={value}\n")
            return jsonify({'success': True, 'message': 'Config updated successfully'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Failed to update config: {str(e)}'})


if __name__ == '__main__':
    # 在 Windows 上使用 5000 端口可能需要管理员权限
    app.run(host='0.0.0.0', port=5000, debug=True)