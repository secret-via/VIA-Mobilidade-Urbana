"""Revisão humana em terminal. Só casos confirmados podem entrar em um dataset."""
import json
import shutil
from pathlib import Path


def review_pending(root=None):
    root = Path(root or Path(__file__).resolve().parents[1])
    queue = root / "data" / "learning_queue"
    names = {"car": 0, "bike": 1, "Big car": 2, "people": 3}
    for metadata_path in sorted((queue / "pending").glob("*.json")):
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        prediction = data["prediction"]
        print(f"\n{data['image']} | previsão: {prediction['class_name']} | confiança: {prediction['confidence']:.2f}")
        action = input("[c]onfirmar, c[o]rrigir, [r]ejeitar, [u]ncertain, [i]gnorar: ").strip().lower()
        if action == "i": continue
        destination_name = {"c": "approved", "o": "approved", "r": "rejected", "u": "uncertain"}.get(action)
        if not destination_name:
            print("Opção inválida; caso mantido em pending."); continue
        if action in {"c", "o"}:
            label = prediction["class_id"]
            if action == "o":
                print("Classes:", names)
                label = int(input("ID confirmado: ").strip())
                if label not in names.values(): print("ID inválido; caso mantido."); continue
            print("Informe bbox YOLO x_center y_center width height (ou vazio para não aprovar):")
            bbox = input("> ").strip().split()
            if len(bbox) != 4: print("Sem label confirmado; movendo para uncertain."); destination_name = "uncertain"
            else: data["confirmed_label"], data["bbox_yolo"] = label, bbox
        data["review"] = destination_name
        target = queue / destination_name
        shutil.move(str(metadata_path), str(target / metadata_path.name))
        image = metadata_path.with_name(data["image"])
        if image.exists(): shutil.move(str(image), str(target / image.name))
        (target / metadata_path.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
