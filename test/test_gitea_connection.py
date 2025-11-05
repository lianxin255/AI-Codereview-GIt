#!/usr/bin/env python3
"""
Gitea 连接测试脚本

用于测试 Docker 容器是否能正确访问 Gitea API
"""

import os
import sys
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv("conf/.env")

def print_section(title):
    """打印分隔标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def test_env_config():
    """测试环境变量配置"""
    print_section("1. 检查环境变量配置")
    
    gitea_url = os.getenv("GITEA_URL")
    gitea_token = os.getenv("GITEA_ACCESS_TOKEN")
    
    if not gitea_url:
        print("❌ 错误: GITEA_URL 未配置")
        return False
    
    if not gitea_token:
        print("❌ 错误: GITEA_ACCESS_TOKEN 未配置")
        return False
    
    print(f"✅ GITEA_URL: {gitea_url}")
    print(f"✅ GITEA_ACCESS_TOKEN: {'*' * 10}{gitea_token[-4:] if len(gitea_token) > 4 else '****'}")
    
    # 检查是否使用了错误的配置
    if "127.0.0.1" in gitea_url or "localhost" in gitea_url:
        print("\n⚠️  警告: 检测到使用 127.0.0.1 或 localhost")
        print("   在 Docker 容器中，这些地址会指向容器本身而不是宿主机")
        print("   建议使用:")
        print("   - 域名: http://yourdomain.com:port")
        print("   - Docker Desktop: http://host.docker.internal:port")
        print("   - Linux 宿主机: http://实际IP地址:port")
        return False
    
    return True

def test_network_connection():
    """测试网络连接"""
    print_section("2. 测试网络连接")
    
    gitea_url = os.getenv("GITEA_URL")
    
    try:
        # 测试 Gitea 版本 API
        version_url = f"{gitea_url}/api/v1/version"
        print(f"请求 URL: {version_url}")
        
        response = requests.get(version_url, timeout=10, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 连接成功!")
            print(f"   Gitea 版本: {data.get('version', 'unknown')}")
            return True
        else:
            print(f"❌ 连接失败: HTTP {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ 连接错误: 无法连接到 {gitea_url}")
        print(f"   错误详情: {str(e)}")
        print("\n可能的原因:")
        print("   1. Gitea 服务未启动")
        print("   2. URL 配置错误（如使用了 127.0.0.1）")
        print("   3. 端口号错误")
        print("   4. 防火墙阻止")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {str(e)}")
        return False

def test_authentication():
    """测试认证"""
    print_section("3. 测试 Token 认证")
    
    gitea_url = os.getenv("GITEA_URL")
    gitea_token = os.getenv("GITEA_ACCESS_TOKEN")
    
    try:
        # 测试用户 API（需要认证）
        user_url = f"{gitea_url}/api/v1/user"
        headers = {"Authorization": f"token {gitea_token}"}
        
        print(f"请求 URL: {user_url}")
        response = requests.get(user_url, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 认证成功!")
            print(f"   用户名: {data.get('login', 'unknown')}")
            print(f"   邮箱: {data.get('email', 'unknown')}")
            return True
        elif response.status_code == 401:
            print(f"❌ 认证失败: Token 无效或已过期")
            print(f"   请检查 GITEA_ACCESS_TOKEN 是否正确")
            return False
        else:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        return False

def test_repo_access():
    """测试仓库访问（需要用户输入仓库信息）"""
    print_section("4. 测试仓库访问（可选）")
    
    gitea_url = os.getenv("GITEA_URL")
    gitea_token = os.getenv("GITEA_ACCESS_TOKEN")
    
    print("\n请输入要测试的仓库信息（直接回车跳过）:")
    owner = input("  仓库所有者 (owner): ").strip()
    
    if not owner:
        print("⏭️  跳过仓库访问测试")
        return None
    
    repo = input("  仓库名称 (repo): ").strip()
    
    if not repo:
        print("⏭️  跳过仓库访问测试")
        return None
    
    try:
        # 测试仓库 API
        repo_url = f"{gitea_url}/api/v1/repos/{owner}/{repo}"
        headers = {"Authorization": f"token {gitea_token}"}
        
        print(f"\n请求 URL: {repo_url}")
        response = requests.get(repo_url, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 仓库访问成功!")
            print(f"   仓库全名: {data.get('full_name', 'unknown')}")
            print(f"   是否私有: {data.get('private', False)}")
            return True
        elif response.status_code == 404:
            print(f"❌ 仓库不存在或无权访问")
            return False
        else:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        return False

def test_pull_request_api():
    """测试 Pull Request API"""
    print_section("5. 测试 Pull Request API（可选）")
    
    gitea_url = os.getenv("GITEA_URL")
    gitea_token = os.getenv("GITEA_ACCESS_TOKEN")
    
    print("\n请输入要测试的 PR 信息（直接回车跳过）:")
    owner = input("  仓库所有者 (owner): ").strip()
    
    if not owner:
        print("⏭️  跳过 PR API 测试")
        return None
    
    repo = input("  仓库名称 (repo): ").strip()
    pr_index = input("  PR 编号: ").strip()
    
    if not repo or not pr_index:
        print("⏭️  跳过 PR API 测试")
        return None
    
    try:
        # 测试 PR files API
        files_url = f"{gitea_url}/api/v1/repos/{owner}/{repo}/pulls/{pr_index}/files"
        headers = {
            "Authorization": f"token {gitea_token}",
            "Content-Type": "application/json"
        }
        
        print(f"\n请求 URL: {files_url}")
        response = requests.get(files_url, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            files = response.json()
            print(f"✅ PR 文件列表获取成功!")
            print(f"   变更文件数: {len(files)}")
            
            # 检查是否有 patch 字段
            has_patch = False
            for file in files:
                if file.get("patch"):
                    has_patch = True
                    break
            
            if has_patch:
                print("   ✅ 包含 patch 数据")
            else:
                print("   ⚠️  不包含 patch 数据（会自动从 .diff 端点获取）")
            
            # 测试 .diff 端点
            diff_url = f"{gitea_url}/api/v1/repos/{owner}/{repo}/pulls/{pr_index}.diff"
            print(f"\n尝试获取完整 diff: {diff_url}")
            diff_response = requests.get(diff_url, headers=headers, timeout=10, verify=False)
            
            if diff_response.status_code == 200:
                diff_content = diff_response.text
                print(diff_content)
                print(f"   ✅ .diff 端点可用 (共 {len(diff_content)} 字节)")
            else:
                print(f"   ⚠️  .diff 端点不可用: HTTP {diff_response.status_code}")
            
            return True
        elif response.status_code == 404:
            print(f"❌ PR 不存在")
            return False
        else:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        return False

def main():
    """主函数"""
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  Gitea 连接测试工具".center(56) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "═" * 58 + "╝")
    
    results = []
    
    # 测试 1: 环境变量
    results.append(("环境变量配置", test_env_config()))
    
    if not results[0][1]:
        print("\n⚠️  请先修复环境变量配置问题")
        sys.exit(1)
    
    # 测试 2: 网络连接
    results.append(("网络连接", test_network_connection()))
    
    if not results[1][1]:
        print("\n⚠️  请先解决网络连接问题")
        sys.exit(1)
    
    # 测试 3: 认证
    results.append(("Token 认证", test_authentication()))
    
    # 测试 4: 仓库访问（可选）
    repo_result = test_repo_access()
    if repo_result is not None:
        results.append(("仓库访问", repo_result))
    
    # 测试 5: PR API（可选）
    pr_result = test_pull_request_api()
    if pr_result is not None:
        results.append(("PR API", pr_result))
    
    # 打印总结
    print_section("测试结果总结")
    
    all_passed = True
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {name}: {status}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("\n🎉 所有测试通过! Gitea 配置正确，可以正常使用。")
        print("\n下一步:")
        print("  1. 在 Gitea 仓库中配置 Webhook")
        print("  2. Webhook URL: http://your-server-ip:5001/review/webhook")
        print("  3. 触发事件: Pull Request, Push")
        print("  4. 创建测试 PR 验证功能")
    else:
        print("\n⚠️  部分测试失败，请根据上述错误信息进行修复。")
        print("\n参考文档:")
        print("  - GITEA_CONFIG_GUIDE.md")
        print("  - GITEA_API_FIX.md")
        print("  - doc/faq.md")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n测试已取消")
        sys.exit(1)

