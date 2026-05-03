import re
import os

# 读取章节名称
chapters_path = os.path.join("test_output", "红楼梦章节名称.txt")
with open(chapters_path, "r", encoding="utf-8") as f:
    chapters = [line.strip() for line in f if line.strip()]

print(f"共读取 {len(chapters)} 个章节")

# 读取人物名单，提取所有人名（排除分类标题等非人名行）
characters_path = os.path.join("test_output", "红楼梦人物.txt")
with open(characters_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 提取人名：匹配 "- XXX" 格式的行，以及括号内 "（" 之前的名字
characters = []
for line in lines:
    line = line.strip()
    # 匹配以 "- " 开头的行
    if line.startswith("- "):
        name_part = line[2:].strip()
        # 取括号前的名字（去掉别名/备注）
        name = name_part.split("（")[0].split("(")[0].strip()
        if name:
            characters.append(name)

print(f"共提取 {len(characters)} 个人名")
print("人名列表:", characters)

# 匹配每个人名出现在哪些章节
result_lines = []
for char in characters:
    matched_chapters = []
    for i, chapter in enumerate(chapters):
        # 在章节标题中查找人名
        if char in chapter:
            # 提取章节序号
            chapter_num = re.match(r"第[一二三四五六七八九十百]+回", chapter)
            if chapter_num:
                matched_chapters.append(chapter_num.group())
            else:
                matched_chapters.append(f"第{i+1}回")
    
    if matched_chapters:
        result_lines.append(f"{char}：{'、'.join(matched_chapters)}")
    else:
        result_lines.append(f"{char}：未在章节标题中出现")

# 写入结果
output_path = os.path.join("test_output", "红楼梦章节人物.txt")
with open(output_path, "w", encoding="utf-8") as f:
    f.write("红楼梦人物与出现章节对照表\n")
    f.write("=" * 50 + "\n\n")
    f.write("\n".join(result_lines))

print(f"\n结果已写入 {output_path}")
print(f"共 {len(result_lines)} 个人物匹配记录")
