# Webui Cost tracking
https://docs.litellm.ai/docs/proxy/forward_client_headers

use scripts/new-user-creation.py to ensure the id are the same uuid in both open-webui and litellm (even without SSO)

# Webui Skills

# Webui Prompts

# Webui MCP

# Litellm MCP

# Integration with opencode
https://docs.litellm.ai/docs/tutorials/opencode_integration

1. 安装 Windows (WSL) | OpenCode https://opencode.ai/docs/windows-wsl/
  1. 把加到 ~/.bashrc 的内容加到 ~/.bash_profile
```
wls --shutdown
```
  2.设置：禁用免费模型，避免发生数据泄露
```
pico ~/.config/opencode/opencode.json
```
```
{
  "$schema": "https://opencode.ai/config.json",
  "disabled_providers": ["opencode"],
}
```
2. 使用公司大模型 OpenCode Quickstart | liteLLM https://docs.litellm.ai/docs/tutorials/opencode_integration

  1. Add the following into config
```
pico ~/.config/opencode/opencode.json
```

```
  "provider": {
    "litellm": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LiteLLM",
      "options": {
        "baseURL": "https://ai-api-test.igus-app.cn/v1"
      },
      "models": {
        "gpt-5-Nano": {
          "name": "gpt-5-Nano",
          "attachment": true,
          "reasoning": false,
          "temperature": true,
          "tool_call": true,
          "cost": {
            "input": 0.0025,
            "output": 0.01
          },
          "options": {
             "reasoningSummary": null,
          },
          "limit": {
            "context": 272000,
            "output": 128000
          }
        }
      }
    }
  },
```
2. 运行 opencode
3. Ctrl+P Provider，输key（在Litellm生成，没有的找Titus）
4. 解决ReasonSummary问题：https://github.com/anomalyco/opencode/issues/13546#issuecomment-3953254864
5. 调整Context问题https://github.com/anomalyco/opencode/issues/7705#issuecomment-3735477810



3. MCP 
```
TODO
```

4. Skills
  1. GitHub - obra/superpowers: An agentic skills framework & software development methodology that work… https://github.com/obra/superpowers
     1. Type the following into opencode
```
Fetch and follow instructions from https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/.opencode/INSTALL.md
```

5. Agents

  1. TODO: ADD MULTIPLE AGENTS: oh-my-opencode GitHub - code-yeongyu/oh-my-opencode: the best agent harness https://github.com/code-yeongyu/oh-my-opencode

```
Install and configure oh-my-opencode by following the instructions here:
https://raw.githubusercontent.com/code-yeongyu/oh-my-opencode/refs/heads/master/docs/guide/installa…
```

  2.[Feature]: Allow switching to native build/plan modes without restarting - let user choose · Issue … - to get back default "Plan" "Build" mode https://github.com/code-yeongyu/oh-my-opencode/issues/1181
