#!/bin/bash
# manga-translator 清理脚本
# 清理翻译流水线产生的临时文件和过期数据
# 用法: bash cleanup.sh [选项]
#   --all        清理所有（input+output+result）
#   --input      仅清理 input 目录
#   --output     仅清理 output 目录
#   --result     仅清理 result 目录
#   --dry-run    预览模式，不实际删除
#   --keep N     保留 output 下最近 N 个翻译结果（默认 3）

set -e

BASE_DIR="/root/manga-translator"
DRY_RUN=false
CLEAN_INPUT=false
CLEAN_OUTPUT=false
CLEAN_RESULT=false
KEEP_OUTPUT=3

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all) CLEAN_INPUT=true; CLEAN_OUTPUT=true; CLEAN_RESULT=true ;;
        --input) CLEAN_INPUT=true ;;
        --output) CLEAN_OUTPUT=true ;;
        --result) CLEAN_RESULT=true ;;
        --dry-run) DRY_RUN=true ;;
        --keep) KEEP_OUTPUT="$2"; shift ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
    shift
done

# 默认清理所有
if ! $CLEAN_INPUT && ! $CLEAN_OUTPUT && ! $CLEAN_RESULT; then
    CLEAN_INPUT=true
    CLEAN_OUTPUT=true
    CLEAN_RESULT=true
fi

do_rm() {
    if $DRY_RUN; then
        echo "  [预览] 将删除: $1"
    else
        rm -rf "$1" 2>/dev/null || true
    fi
}

get_size() {
    du -sh "$1" 2>/dev/null | cut -f1 || echo "0"
}

echo "========================================"
echo "  manga-translator 清理脚本"
if $DRY_RUN; then
    echo "  ⚠️  预览模式 — 不会实际删除"
fi
echo "========================================"

# ── 清理 result/ 中间产物 ──
if $CLEAN_RESULT; then
    echo ""
    echo "📁 清理 result/ 中间产物..."
    
    # 清理所有 timestamp-UUID-2048-CHS-* 目录（中间过程输出）
    COUNT=0
    for dir in "$BASE_DIR"/result/[0-9]*-*/; do
        [ -d "$dir" ] || continue
        do_rm "$dir"
        COUNT=$((COUNT + 1))
    done
    
    # 清理日志（保留最近 5 个）
    LOG_COUNT=$(ls -1t "$BASE_DIR"/result/log_*.txt 2>/dev/null | wc -l)
    if [ "$LOG_COUNT" -gt 5 ]; then
        LOGS_TO_DEL=$(ls -1t "$BASE_DIR"/result/log_*.txt 2>/dev/null | tail -n +6)
        for log in $LOGS_TO_DEL; do
            do_rm "$log"
        done
        echo "  清理了 $(echo "$LOGS_TO_DEL" | wc -l) 个旧日志文件"
    fi
    
    echo "  清理了 $COUNT 个中间产物目录"
    echo "  当前 result/ 大小: $(get_size "$BASE_DIR"/result)"
fi

# ── 清理 input/ 原图 ──
if $CLEAN_INPUT; then
    echo ""
    echo "📁 清理 input/ 原图下载..."
    
    COUNT=0
    for dir in "$BASE_DIR"/input/*/; do
        [ -d "$dir" ] || continue
        # 清理 gallery-dl 下载的目录和单个目录
        do_rm "$dir"
        COUNT=$((COUNT + 1))
    done
    
    echo "  清理了 $COUNT 个输入目录"
    echo "  当前 input/ 大小: $(get_size "$BASE_DIR"/input)"
fi

# ── 清理 output/ 翻译结果 ──
if $CLEAN_OUTPUT; then
    echo ""
    echo "📁 清理 output/ 翻译结果（保留最近 $KEEP_OUTPUT 个）..."
    
    TOTAL=$(ls -1dt "$BASE_DIR"/output/*/ 2>/dev/null | wc -l)
    if [ "$TOTAL" -gt "$KEEP_OUTPUT" ]; then
        TO_DELETE=$(ls -1dt "$BASE_DIR"/output/*/ 2>/dev/null | tail -n +$((KEEP_OUTPUT + 1)))
        COUNT=0
        for dir in $TO_DELETE; do
            do_rm "$dir"
            COUNT=$((COUNT + 1))
        done
        echo "  清理了 $COUNT 个旧翻译结果（共 $TOTAL 个，保留 $KEEP_OUTPUT 个）"
    else
        echo "  无需清理（共 $TOTAL 个，≤保留数 $KEEP_OUTPUT）"
    fi
    echo "  当前 output/ 大小: $(get_size "$BASE_DIR"/output)"
fi

# ── 清理 /tmp 残留 ──
echo ""
echo "📁 清理 /tmp 临时文件..."
TMP_COUNT=$(find /tmp -maxdepth 3 \( -name "*manga*" -o -name "*translate*" -o -name "*catbox*" -o -name "*telegraph*" -o -name "publish_*" \) 2>/dev/null | wc -l)
if [ "$TMP_COUNT" -gt 0 ]; then
    if $DRY_RUN; then
        find /tmp -maxdepth 3 \( -name "*manga*" -o -name "*translate*" -o -name "*catbox*" -o -name "*telegraph*" -o -name "publish_*" \) -print 2>/dev/null
    else
        find /tmp -maxdepth 3 \( -name "*manga*" -o -name "*translate*" -o -name "*catbox*" -o -name "*telegraph*" -o -name "publish_*" \) -delete 2>/dev/null
    fi
    echo "  清理了 $TMP_COUNT 个临时文件"
else
    echo "  无残留"
fi

# ── 汇总 ──
echo ""
echo "========================================"
echo "  清理完成"
echo "  result/ : $(get_size "$BASE_DIR"/result)"
echo "  input/  : $(get_size "$BASE_DIR"/input)"
echo "  output/ : $(get_size "$BASE_DIR"/output)"
echo "  models/ : $(get_size "$BASE_DIR"/models) (保留)"
echo "========================================"
