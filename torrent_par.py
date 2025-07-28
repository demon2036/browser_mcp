#!/usr/bin/env python3
"""
精简版种子解析器 - 支持本地文件和Info Hash查询
依赖：pip install bencode.py requests
"""

import bencodepy
import hashlib
import requests
import json
from pathlib import Path
from typing import Dict, List, Optional, Union


class TorrentParser:
    """精简的种子解析器"""

    # 使用公开的种子信息API（备选方案）
    TORRENT_APIS = [
        "https://itorrents.org/torrent/{}.torrent",  # 直接下载种子
        "https://torrage.info/torrent.php?h={}",  # Torrage缓存
    ]

    @staticmethod
    def parse_torrent(torrent_path: Union[str, Path, bytes]) -> Dict:
        """解析种子文件或数据"""
        if isinstance(torrent_path, bytes):
            data = bencodepy.decode(torrent_path)
        else:
            with open(torrent_path, 'rb') as f:
                data = bencodepy.decode(f.read())

        info = data['info']
        info_hash = hashlib.sha1(bencodepy.encode(info)).hexdigest()

        # 提取文件信息
        files = []
        total_size = 0

        if b'files' in info:  # 多文件
            for f in info[b'files']:
                file_path = '/'.join(p.decode('utf-8', errors='ignore') for p in f[b'path'])
                file_size = f[b'length']
                files.append({'path': file_path, 'size': file_size})
                total_size += file_size
        else:  # 单文件
            name = info[b'name'].decode('utf-8', errors='ignore')
            size = info[b'length']
            files.append({'path': name, 'size': size})
            total_size = size

        return {
            'name': info[b'name'].decode('utf-8', errors='ignore'),
            'info_hash': info_hash,
            'files': files,
            'total_size': total_size,
            'trackers': TorrentParser._get_trackers(data)
        }

    @staticmethod
    def _get_trackers(data: dict) -> List[str]:
        """提取tracker列表"""
        trackers = []
        if b'announce' in data:
            trackers.append(data[b'announce'].decode('utf-8', errors='ignore'))
        if b'announce-list' in data:
            for tier in data[b'announce-list']:
                for tracker in tier:
                    trackers.append(tracker.decode('utf-8', errors='ignore'))
        return list(set(trackers))  # 去重

    @staticmethod
    def parse_magnet(magnet_uri: str) -> Dict:
        """解析磁力链接"""
        if not magnet_uri.startswith('magnet:?'):
            raise ValueError("Invalid magnet link")

        params = {}
        for param in magnet_uri[8:].split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value

        info_hash = None
        if 'xt' in params and params['xt'].startswith('urn:btih:'):
            info_hash = params['xt'][9:].lower()

        return {
            'info_hash': info_hash,
            'name': params.get('dn', 'Unknown'),
            'trackers': [tr for key, tr in params.items() if key == 'tr']
        }

    @staticmethod
    def fetch_by_hash(info_hash: str) -> Optional[Dict]:
        """通过info hash获取种子信息"""
        info_hash = info_hash.upper()

        # 尝试从公开API获取种子文件
        for api_url in TorrentParser.TORRENT_APIS:
            try:
                url = api_url.format(info_hash)
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                if response.status_code == 200:
                    # 解析下载的种子
                    return TorrentParser.parse_torrent(response.content)
            except:
                continue

        # 如果API都失败，尝试使用DHT爬虫服务
        return TorrentParser._fetch_from_dht_crawler(info_hash)

    @staticmethod
    def _fetch_from_dht_crawler(info_hash: str) -> Optional[Dict]:
        """从DHT爬虫服务获取信息（备选方案）"""
        # 这里可以使用一些公开的DHT爬虫API
        # 例如：btdig.com, torrentapi.org等
        # 由于这些服务可能需要API key或有限制，这里只展示结构

        # 示例：使用假想的DHT API
        try:
            # url = f"https://api.example.com/hash/{info_hash}"
            # response = requests.get(url, timeout=10)
            # if response.status_code == 200:
            #     data = response.json()
            #     return {
            #         'name': data.get('name'),
            #         'info_hash': info_hash,
            #         'files': data.get('files', []),
            #         'total_size': data.get('size', 0)
            #     }
            pass
        except:
            pass

        return None

    @staticmethod
    def format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"


def quick_check(torrent_input: str) -> None:
    """快速检查种子内容"""
    parser = TorrentParser()

    # 判断输入类型
    if torrent_input.startswith('magnet:'):
        print("🔍 解析磁力链接...")
        magnet_info = parser.parse_magnet(torrent_input)
        print(f"📋 Info Hash: {magnet_info['info_hash']}")

        # 尝试获取完整信息
        if magnet_info['info_hash']:
            result = parser.fetch_by_hash(magnet_info['info_hash'])
            if result:
                torrent_info = result
            else:
                print("⚠️  无法获取种子详细信息")
                return
        else:
            print("❌ 无效的磁力链接")
            return

    elif len(torrent_input) == 40 and all(c in '0123456789abcdefABCDEF' for c in torrent_input):
        print(f"🔍 通过Info Hash查询: {torrent_input}")
        result = parser.fetch_by_hash(torrent_input)
        if result:
            torrent_info = result
        else:
            print("❌ 无法获取种子信息")
            return

    else:
        print(f"🔍 解析种子文件: {torrent_input}")
        try:
            torrent_info = parser.parse_torrent(torrent_input)
        except Exception as e:
            print(f"❌ 解析失败: {e}")
            return

    # 显示结果
    print(f"\n✅ 种子名称: {torrent_info['name']}")
    print(f"📊 总大小: {parser.format_size(torrent_info['total_size'])}")
    print(f"🔑 Info Hash: {torrent_info['info_hash']}")
    print(f"\n📁 文件列表 ({len(torrent_info['files'])} 个文件):")

    # 显示前10个文件
    for i, file in enumerate(torrent_info['files'][:10]):
        print(f"  {i + 1}. {file['path']} ({parser.format_size(file['size'])})")

    if len(torrent_info['files']) > 10:
        print(f"  ... 还有 {len(torrent_info['files']) - 10} 个文件")


if __name__ == "__main__":
    # 使用示例

    # 1. 解析本地种子文件
    # quick_check("example.torrent")
    quick_check('magnet:?xt=urn:btih:6d79b55d835bb62b5ab76784a31e4f7a1fa97682&dn=%5BNew-raws%5D%20Silent%20Witch%20-%2004%20%5B1080p%5D%20%5BAMZN%5D.mkv&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce')
    quick_check('a097065019ffe30c3b410c3b1b8a898cdd1f1600')
    # 2. 解析info hash
    # quick_check("6d79b55d835bb62b5ab76784a31e4f7a1fa97682")

    # 3. 解析磁力链接
    # quick_check("magnet:?xt=urn:btih:6d79b55d835bb62b5ab76784a31e4f7a1fa97682&dn=Example")

    # 4. 批量验证（适合自动化测试）
    print("\n" + "=" * 50 + "\n")

    # 模拟批量验证
    test_hashes = [
        "6d79b55d835bb62b5ab76784a31e4f7a1fa97682",
        # 添加更多info hash...
    ]

    # for hash_val in test_hashes:
    #     print(f"\n🔄 验证: {hash_val}")
    #     result = TorrentParser.fetch_by_hash(hash_val)
    #     if result:
    #         # 根据文件名判断内容
    #         keywords = ['S01E01', '720p', '1080p', 'COMPLETE', 'mkv', 'mp4']
    #         files_str = ' '.join(f['path'] for f in result['files'])
    #         matched = [kw for kw in keywords if kw in files_str]
    #         print(f"✓ 匹配关键词: {matched}")
    #     else:
    #         print("✗ 无法验证")