import os
import re
import subprocess
from typing import List
import zipfile
from nimrod.tools.bin import JACOCOCLI, JACOCOAGENT, JUNIT, HAMCREST
from nimrod.utils import generate_classpath


class Jacoco:
    def __init__(self, java):
        self.java = java

    # Run java -jar jacococli.jar instrument project_jar --dest dest_jar_instrumented
    def instrument_jar(self, target_jar: str, destination_directory: str):
        error = "error caused by duplicated entry"
        first_attempt = True
        while(error.find("duplicated entry") or error.find("duplicate entry")):
            if (first_attempt or self.dealing_with_duplicated_files_on_jars(target_jar, error)):
                try:
                    params = [
                        '-jar', JACOCOCLI,
                        'instrument', target_jar,
                        '--dest', destination_directory
                    ]
                    return self.exec_java(*params)
                except subprocess.CalledProcessError as e:
                    error = str(e.stdout)
                except Exception as e:
                    error = ""
                first_attempt = False
            else:
                break

    def dealing_with_duplicated_files_on_jars(self, jar_file: str, message_error: str):
        if ("java.util.zip.ZipException:" in message_error):
            message_error = message_error.split("java.util.zip.ZipException:")[1].split("\\n\\tat")[0].replace("\n\tat","")
            file_to_remove = self.parse_duplicated_file(str(message_error))
            if (file_to_remove != None):
                proc = subprocess.Popen("zip -d "+jar_file+" "+file_to_remove,
                                        shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if ("zip warning: name not matched" in str((proc.stdout.readline()))):
                    return False
                else:
                    return True
        return False

    def parse_duplicated_file(self, message_error: str):
        "Exception in thread \"main\" java.util.zip.ZipException: duplicate entry: META-INF/LICENSE.txt"
        x = re.search("duplicate entry\: .*", message_error, re.IGNORECASE)
        if x:
            file_name = str(message_error.split(
                "duplicate entry: ")[1]).split("\n")[0]
            if ("$" in file_name):
                file_name = file_name.split("$")[0]+".class"
            return file_name
        else:
            return None

    # projectJar = jar instrumentado do projeto
    # suite_class = local do arquivo class da suite de testes
    # test_class = nome da classe de teste
    def create_jacoco_exec(self, projectJar: str, suite_class: str, test_class: str):
        classpath = generate_classpath([
            JUNIT, HAMCREST, JACOCOAGENT,
            suite_class, projectJar
        ])
        params = (
            '-classpath', classpath,
            'org.junit.runner.JUnitCore', test_class
        )

        return self.exec_java(*params)

    # jacocoExecDir = local do arquivo jacocoExec
    # classFiles = local do arquivo class da classe alvo dos testes.
    # nameCsvFile = nome do arquivo csv gerado com o report dos testes.
    def generate_csv_report(self, jacoco_exec_dir: str, class_files: str, output_file_name: str):
        params = [
            '-jar', JACOCOCLI,
            'report', jacoco_exec_dir,
            '--classfiles', class_files,
            '--csv', output_file_name
        ]

        return self.exec_java(*params)

    # caminhoJacocoExec = local do arquivo jacocoExec
    # classFiles = local do arquivo class da classe alvo dos testes.
    # localHtmlGerado = arquivo para criacao do report html.
    def generate_html_report(self, jacoco_exec_directory: str, class_files: str, targetClass=None):
        novo_class_file = class_files
        if type(class_files) == list: # tratamento para caso receber uma lista de jars
            class_files = self.adjust_on_list_of_jars(class_files, targetClass)
            novo_class_file = ""
            for i in range(len(class_files)):
                novo_class_file = novo_class_file + class_files[i]
        caminho_jacoco_exec = jacoco_exec_directory + "/jacoco.exec"
        local_html_gerado = jacoco_exec_directory + "/report"
        params = [
            '-jar', JACOCOCLI,
            'report', caminho_jacoco_exec,
            '--classfiles', novo_class_file,
            '--html', local_html_gerado
        ]

        return self.exec_java(*params)

    def exec_java(self, *params):
        return self.java.simple_exec_java(*params)

    def adjust_on_list_of_jars(self, all_jars, class_name):
        best_option = ""
        first_jar_with_class = False
        for jar_file in all_jars:
            if (self.is_class_on_jar(jar_file, class_name)):
                if (first_jar_with_class == False):
                    best_option = jar_file
                    first_jar_with_class = True
                else:
                    if (os.stat(best_option).st_size < os.stat(jar_file).st_size):
                        all_jars.remove(best_option)
                        best_option = jar_file
                    else:
                        all_jars.remove(jar_file)
        return self.compare_jars(all_jars)

    def is_list_of_jars_with_target_class(self, jar_files: str, class_name: str):
        number_of_jars_with_target_class = 0
        for jarFile in jar_files:
            if self.is_class_on_jar(jarFile, class_name):
                number_of_jars_with_target_class += 1

        return number_of_jars_with_target_class > 1

    def is_class_on_jar(self, jar_file: str, class_name):
        archive = zipfile.ZipFile(jar_file, 'r')
        return class_name.replace(".","/")+".class" in archive.namelist()

    def compare_jars(self, list_of_jars: List[str]):
        best_jars: List[str] = []
        for i in range(len(list_of_jars)):
            for j in range(i, int(len(list_of_jars)-1)):
                if (self.is_any_duplicated_class_on_these_files(list_of_jars[i], list_of_jars[j]) == True):
                    if (os.stat(list_of_jars[i]).st_size >= os.stat(list_of_jars[j]).st_size):
                        if (list_of_jars[j] in best_jars):
                            best_jars.remove(list_of_jars[j])
                        if ((list_of_jars[i] in best_jars) == False and self.compare_jars_with_jar(best_jars, list_of_jars[i])):
                            best_jars.append(list_of_jars[i])
                    elif (os.stat(list_of_jars[j]).st_size >= os.stat(list_of_jars[i]).st_size):
                        if (list_of_jars[i] in best_jars):
                            best_jars.remove(list_of_jars[i])
                        if ((list_of_jars[j] in best_jars) == False and self.compare_jars_with_jar(best_jars, list_of_jars[j])):
                            best_jars.append(list_of_jars[j])
                elif ((list_of_jars[j] in best_jars) == False):
                        best_jars.append(list_of_jars[j])

        return len(best_jars) > 0

    def compare_jars_with_jar(self, all_jars, jar):
        for one_jar in all_jars:
            if (self.is_any_duplicated_class_on_these_files(one_jar, jar)):
                return False

        return True

    def is_any_duplicated_class_on_these_files(self, jarOne, jartwo):
        archive = zipfile.ZipFile(jarOne, 'r').namelist()
        archive_two = zipfile.ZipFile(jartwo, 'r').namelist()
        intersection_set = set.intersection(set(archive), set(archive_two))
        return len(intersection_set) > 0