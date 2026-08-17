# =========================
# Coding Agent Main
# =========================

from workflow.coding_graph import create_coding_graph


# 启动Coding Agent方法
def main():
    """
    启动Coding Agent流程
    """

    # 创建Agent工作流
    app = create_coding_graph()

    # 初始化Agent状态
    result = app.invoke(
        {
            "requirement":
                "创建Unity对象池系统",

            "project_path":
                "./sample_project",

            "output_path":
                "./sample_project/ObjectPool.cs",

            "files":
                [],

            "code":
                "",

            "review":
                {},

            "status":
                ""
        }
    )

    print(result)


if __name__ == "__main__":
    main()