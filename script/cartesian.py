import re


def parse_groups(s: str) -> list[list[str]]:
    """从 '{aa,bb,cc}{11,22}{efg,hij}' 中解析出每个候选集合"""
    groups = []
    for part in re.findall(r'\{([^}]*)\}', s):
        # 按逗号拆分，去掉首尾空白，并过滤掉空元素
        items = [item.strip() for item in part.split(',') if item.strip()]
        groups.append(items)
    return groups


def cartesian(s: str) -> list[str]:
    """手写笛卡尔积：迭代累乘"""
    groups = parse_groups(s)
    print(groups)
    result = ['']                      # 初始只有一个空串
    for group in groups:
        new_result = []
        for x in result:
            for w in group:
                new_result.append(x + w)
        print(new_result)
        result = new_result
    return result


if __name__ == "__main__":
    s = "{aa,bb,cc}{11,22}{efg,hij}"
    result = cartesian(s)

    print(f"共 {len(result)} 种组合")
    print("{" + ",".join(result) + "}")
