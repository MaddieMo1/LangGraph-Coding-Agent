# =========================
# Unity Compiler Tool
# =========================
import os
import re
import shutil
import subprocess
import tempfile
import uuid


class UnityCompileTool:
    """
    Unity C#编译工具

    负责:
    1. 调用Unity BatchMode
    2. 执行C#脚本编译
    3. 解析Unity编译错误
    """

    def __init__(
        self,
        unity_path,
        project_path,
        source_path=None,
        timeout=300,
        process_runner=None
    ):
        """
        初始化Unity编译工具

        Args:
            unity_path:
                Unity.exe路径

            project_path:
                Unity工程路径

            source_path:
                待同步的C#代码目录
        """

        self.unity_path = unity_path
        self.project_path = project_path
        self.source_path = source_path
        self.timeout = timeout
        self.process_runner = process_runner


    def system_error(self, message):
        """
        创建系统级错误结果
        """

        return {
            "success": False,
            "system_error": True,
            "errors": [
                {
                    "file": "unknown",
                    "line": 0,
                    "code": "SYSTEM_ERROR",
                    "message": message
                }
            ],
            "synced_files": [],
            "raw": ""
        }


    def validate_environment(self):
        """
        验证Unity Editor和测试工程路径
        """

        if not os.path.isfile(
            self.unity_path
        ):
            return self.system_error(
                f"Unity Editor不存在:{self.unity_path}"
            )


        project_version = os.path.join(
            self.project_path,
            "ProjectSettings",
            "ProjectVersion.txt"
        )


        if not os.path.isfile(
            project_version
        ):
            return self.system_error(
                f"Unity测试工程无效:{self.project_path}"
            )


        return None


    def sync_scripts(self, project_path=None):
        """
        同步生成代码到Unity测试工程

        Returns:
            已同步的文件名列表
        """

        if not self.source_path:
            return []


        if not os.path.isdir(
            self.source_path
        ):
            raise FileNotFoundError(
                f"生成代码目录不存在:{self.source_path}"
            )


        source_files = [
            file_name
            for file_name in os.listdir(
                self.source_path
            )
            if file_name.endswith(
                ".cs"
            )
        ]


        if not source_files:
            raise FileNotFoundError(
                f"生成代码目录中没有C#文件:{self.source_path}"
            )


        target_path = os.path.join(
            project_path or self.project_path,
            "Assets",
            "Generated"
        )


        os.makedirs(
            target_path,
            exist_ok=True
        )


        for file_name in os.listdir(
            target_path
        ):

            if not (
                file_name.endswith(
                    ".cs"
                )
                or
                file_name.endswith(
                    ".cs.meta"
                )
            ):
                continue


            os.remove(
                os.path.join(
                    target_path,
                    file_name
                )
            )


        for file_name in source_files:

            shutil.copy2(
                os.path.join(
                    self.source_path,
                    file_name
                ),
                os.path.join(
                    target_path,
                    file_name
                )
            )


        return sorted(
            source_files
        )

    def copy_project(self, sandbox_project):
        os.makedirs(sandbox_project)
        for folder in ("Assets", "Packages", "ProjectSettings"):
            source = os.path.join(self.project_path, folder)
            target = os.path.join(sandbox_project, folder)
            if os.path.isdir(source):
                shutil.copytree(source, target)
            else:
                os.makedirs(target)

    def compile(self):
        """
        执行Unity编译

        Returns:
            编译结果
        """

        environment_error = self.validate_environment()


        if environment_error:
            return environment_error


        sandbox_root = tempfile.mkdtemp(prefix="coding-agent-unity-compile-")
        sandbox_project = os.path.join(sandbox_root, "Project")
        result_data = None

        try:
            self.copy_project(sandbox_project)
            synced_files = self.sync_scripts(sandbox_project)

            log_directory = os.path.join(sandbox_project, "Logs")
            os.makedirs(log_directory, exist_ok=True)
            log_path = os.path.join(
                log_directory,
                "coding-agent-compile-" + uuid.uuid4().hex + ".log"
            )

            command = [
                self.unity_path,
                "-batchmode",
                "-quit",
                "-projectPath",
                sandbox_project,
                "-logFile",
                log_path
            ]

            runner = self.process_runner or subprocess.run
            result = runner(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout
            )

            output = result.stdout + result.stderr


            if os.path.isfile(
                log_path
            ):

                with open(
                    log_path,
                    "r",
                    encoding="utf-8",
                    errors="replace"
                ) as log_file:

                    output += log_file.read()

            errors = self.parse_errors(
                output
            )

            if result.returncode != 0 and not errors:
                if "No valid Unity Editor license found" in output:
                    system_result = self.system_error(
                        "Unity Editor 许可证不可用，请先在 Unity Hub 登录并激活许可证后重试"
                    )
                    system_result["errors"][0]["code"] = "UNITY_LICENSE_UNAVAILABLE"
                else:
                    system_result = self.system_error(
                        f"Unity进程异常退出，退出码:{result.returncode}"
                    )

                system_result["synced_files"] = synced_files
                system_result["raw"] = output

                result_data = system_result
            else:
                result_data = {
                    "success": len(errors) == 0,
                    "system_error": False,
                    "errors": errors,
                    "synced_files": synced_files,
                    "raw": output
                }

        except subprocess.TimeoutExpired:
            result_data = self.system_error(
                f"Unity 编译超时，超过 {self.timeout} 秒"
            )
            result_data["errors"][0]["code"] = "UNITY_TIMEOUT"
        except Exception as e:
            result_data = self.system_error(str(e))
        finally:
            shutil.rmtree(sandbox_root, ignore_errors=True)

        result_data["sandbox_project"] = sandbox_project
        result_data["sandbox_cleaned"] = not os.path.exists(sandbox_root)
        return result_data


    def parse_errors(self, log):
        """
        解析Unity C#编译错误

        Args:
            log:
                Unity Console日志

        Returns:
            结构化错误列表
        """

        errors = []
        seen = set()

        pattern = (
            r"(?P<file>[^\s]+\.cs)"
            r"\((?P<line>\d+),\d+\)"
            r": error (?P<code>CS\d+):"
            r" (?P<message>.*)"
        )


        for line in log.splitlines():

            match = re.search(
                pattern,
                line
            )

            if match:

                file_name = os.path.basename(
                    match.group(
                        "file"
                    ).replace(
                        "\\",
                        "/"
                    )
                )


                line_number = int(
                    match.group(
                        "line"
                    )
                )


                code = match.group(
                    "code"
                )


                message = match.group(
                    "message"
                )


                key = (
                    file_name,
                    line_number,
                    code,
                    message
                )


                if key in seen:
                    continue


                seen.add(
                    key
                )

                errors.append(
                    {
                        "file":
                        file_name,

                        "line":
                        line_number,

                        "code":
                        code,

                        "message":
                        message
                    }
                )


        return errors
