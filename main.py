import subprocess
import sys
from pathlib import Path


def main():
    choice = input("1 - Webcam\n2 - Vídeo\n3 - Maquete\n4 - Revisar casos de aprendizagem\n5 - Criar versão de dataset\nEscolha: ").strip()
    scripts = Path(__file__).resolve().parent / "scripts"
    if choice == "1":
        subprocess.run([sys.executable, str(scripts / "detectar_webcam.py")], check=False)
    elif choice == "2":
        source = input("Caminho do vídeo: ").strip()
        if source:
            subprocess.run([sys.executable, str(scripts / "detectar_video.py"), "--source", source], check=False)
    elif choice == "3":
        subprocess.run([sys.executable, str(scripts / "detectar_maquete.py")], check=False)
    elif choice == "4":
        subprocess.run([sys.executable, str(scripts / "revisar_casos.py")], check=False)
    elif choice == "5":
        subprocess.run([sys.executable, str(scripts / "criar_dataset.py")], check=False)
    else:
        print("Opção inválida.")


if __name__ == "__main__":
    main()
