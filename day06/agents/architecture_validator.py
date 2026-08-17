# =========================
# Architecture Validator
# =========================


class ArchitectureValidator:
    """
    架构验证Agent

    负责:
    1. 检查文件规划合理性
    2. 检测模块职责冲突
    3. 防止错误架构进入Coder阶段
    """

    def __init__(self, llm=None):
        """
        初始化架构验证Agent

        Args:
            llm:
                大语言模型实例
        """

        self.llm = llm

    def validate(self, files):
        """
        验证文件规划

        Args:
            files:
                File Planner生成的文件列表

        Returns:
            dict:
                架构检查结果
        """

        normalized_files = []

        # 兼容字符串和字典格式
        for file in files:

            if isinstance(file, str):

                normalized_files.append(
                    {
                        "name": file,
                        "description": ""
                    }
                )

            else:

                normalized_files.append(
                    {
                        "name": file.get(
                            "name",
                            ""
                        ),
                        "description": file.get(
                            "description",
                            ""
                        )
                    }
                )

        names = [
            file["name"]
            for file in normalized_files
        ]

        errors = []

        # 检查System和Manager冲突
        for name in names:

            if "System" in name:

                manager_name = name.replace(
                    "System",
                    "Manager"
                )

                if manager_name in names:

                    errors.append(
                        f"禁止同时存在{name}和{manager_name}"
                    )


        # 检查重复Data文件

        data_files = [
            name
            for name in names
            if "Data" in name
        ]

        if len(data_files) > 1:

            errors.append(
                "存在多个数据模型文件"
            )


        # 检查UI职责污染

        for file in normalized_files:

            name = file["name"]

            description = file["description"]


            if (
                "Panel" in name
                or "View" in name
            ):

                keywords = [
                    "数据模型",
                    "ItemData",
                    "ItemType",
                    "实体"
                ]

                for keyword in keywords:

                    if keyword in description:

                        errors.append(
                            f"{name}不允许包含{keyword}"
                        )


        result = {
            "pass": len(errors) == 0,
            "errors": errors
        }


        if result["pass"]:

            print(
                "[Architecture Validator]架构检查通过"
            )

        else:

            print(
                f"[Architecture Validator]发现问题:{errors}"
            )


        return result