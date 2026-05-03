# -*- coding: utf-8 -*-
import os

# 1. 读取章节标题
base_dir = r'D:\Pyprogram\learn-claude-codetest'
title_path = os.path.join(base_dir, 'test_output', '红楼梦章节名称.txt')

with open(title_path, 'r', encoding='utf-8') as f:
    titles = f.readlines()

# 清理标题
titles = [t.strip() for t in titles if t.strip()]

print(f"共读取 {len(titles)} 回章节标题")

# 2. 定义人物及其别称
characters = {
    "贾宝玉": ["贾宝玉", "宝玉"],
    "贾母": ["贾母", "史太君"],
    "贾政": ["贾政", "政老"],
    "王夫人": ["王夫人"],
    "贾赦": ["贾赦"],
    "邢夫人": ["邢夫人"],
    "贾珍": ["贾珍"],
    "尤氏": ["尤氏"],
    "贾琏": ["贾琏"],
    "王熙凤": ["王熙凤", "王凤姐", "凤姐", "熙凤"],
    "贾元春": ["贾元春", "元妃", "元春"],
    "贾迎春": ["贾迎春", "迎春"],
    "贾探春": ["贾探春", "探春"],
    "贾惜春": ["贾惜春", "惜春"],
    "贾兰": ["贾兰"],
    "贾环": ["贾环"],
    "贾蓉": ["贾蓉"],
    "秦可卿": ["秦可卿"],
    "李纨": ["李纨"],
    "林黛玉": ["林黛玉", "黛玉", "潇湘妃子", "潇湘", "颦卿", "颦儿"],
    "薛宝钗": ["薛宝钗", "宝钗", "蘅芜君", "蘅芜"],
    "史湘云": ["史湘云", "湘云"],
    "妙玉": ["妙玉"],
    "巧姐": ["巧姐"],
    "薛姨妈": ["薛姨妈"],
    "薛蟠": ["薛蟠", "薛文龙", "薛文起", "呆霸王"],
    "香菱": ["香菱", "英莲"],
    "夏金桂": ["夏金桂", "金桂"],
    "袭人": ["袭人"],
    "晴雯": ["晴雯"],
    "紫鹃": ["紫鹃"],
    "莺儿": ["莺儿"],
    "平儿": ["平儿"],
    "鸳鸯": ["鸳鸯"],
    "司棋": ["司棋"],
    "麝月": ["麝月"],
    "小红": ["小红"],
    "刘姥姥": ["刘姥姥"],
    "甄士隐": ["甄士隐"],
    "贾雨村": ["贾雨村", "雨村"],
    "尤二姐": ["尤二姐", "尤二姨"],
    "尤三姐": ["尤三姐"],
    "柳湘莲": ["柳湘莲", "冷二郎", "柳二郎"],
    "赵姨娘": ["赵姨娘"],
    "贾瑞": ["贾瑞"],
    "蒋玉菡": ["蒋玉菡"],
    "马道婆": ["马道婆"],
}

# 3. 统计出现次数
# 需要处理重叠匹配的问题，比如"宝玉"和"贾宝玉"，"宝钗"和"薛宝钗"等
# 策略：对于每个标题，先匹配较长的名字，避免重复计数

def count_in_titles(titles, names_list):
    """统计一组名字在标题中出现的总次数（每个标题最多计1次，避免同一个标题重复统计同一个人物的不同别称）"""
    count = 0
    for title in titles:
        for name in names_list:
            if name in title:
                count += 1
                break  # 一个标题中同一个人物只计1次
    return count

results = []
for person, names in characters.items():
    cnt = count_in_titles(titles, names)
    if cnt > 0:
        results.append((person, cnt))

# 按次数从高到低排序
results.sort(key=lambda x: x[1], reverse=True)

# 4. 写入结果
output_path = os.path.join(base_dir, 'test_output', '红楼梦章节人物频率.txt')
with open(output_path, 'w', encoding='utf-8') as f:
    f.write("红楼梦章节标题人物出现频率统计\n")
    f.write("====================================\n")
    for person, cnt in results:
        f.write(f"{person}: {cnt} 次\n")

print(f"结果已写入 {output_path}")
print(f"共 {len(results)} 个人物出现")
for person, cnt in results:
    print(f"{person}: {cnt} 次")
