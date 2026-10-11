name: 墨线检查流水线

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality-check:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout 仓库
        uses: actions/checkout@v4

      # ---------- 环境在准备 ----------
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '22'   # story-cli 要求 Node.js >= 22

      # ---------- 1. 字数统计与章节标题检查 ----------
      - name: 安装 story-cli
        run: npm install -g @yuelinghuashu/story-cli

      - name: 字数统计与章节标题提取
        run: |
          echo "=== 字数统计 ==="
          story stats
          echo ""
          echo "=== 章节校验 ==="
          story validate
        continue-on-error: true

      # ---------- 2. 写作风格与 AI 痕迹检测（WSC） ----------
      - name: 运行 Writing Style Checker
        uses: theserverlessdev/wsc/action@master
        with:
          files: '《影笔代理人》/正文/**/*.md'
          format: github          # 输出 GitHub ::warning 注解
          # 如需失败阈值，取消注释下一行
          # max-warnings: 20
        continue-on-error: true

      # ---------- 3. 时间线一致性检查 ----------
      - name: 安装 timeline-check Skill
        run: npx skills add https://github.com/QGG886/novel_creator --skill timeline-check

      - name: 时间线一致性分析
        run: |
          npx skills run timeline-check \
            --path "《影笔代理人》/连续性/时间线.yaml" \
            --chapters "《影笔代理人》/正文/"
        continue-on-error: true

      # ---------- 4. 伏笔追踪 ----------
      - name: 安装 foreshadow-tracker
        run: npx skills add https://github.com/vastth/ARMA3-ZeusCut-Remastered --skill foreshadow-tracker

      - name: 伏笔状态扫描
        run: |
          npx skills run foreshadow-tracker scan \
            --foreshadow-file "《影笔代理人》/连续性/伏笔.yaml"
        continue-on-error: true

      # ---------- 5. 叙事质量深度检查（novel-bug-checker） ----------
      - name: 安装 novel-bug-checker 依赖
        run: pip install jieba

      - name: 克隆 novel-bug-checker
        run: |
          git clone https://github.com/bbroot/novel-bug-checker.git /tmp/novel-bug-checker

      - name: 逻辑漏洞与角色一致性分析
        run: |
          # 将所有正文合并为一个文本供分析
          find "《影笔代理人》/正文" -name "第*.md" -exec cat {} \; > /tmp/novel_full.txt
          python /tmp/novel-bug-checker/scripts/logic-analyzer.py /tmp/novel_full.txt -o /tmp/logic-report.txt
          echo "=== 逻辑分析报告 ==="
          cat /tmp/logic-report.txt
        continue-on-error: true

      # ---------- 6. 汇总报告 ----------
      - name: 上传检查报告
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: 墨线检查报告
          path: |
            /tmp/logic-report.txt
            log/检查.txt