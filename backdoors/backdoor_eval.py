from lavis.models import load_model_and_preprocess
import torch
from PIL import Image
import argparse
import os
import json
import yaml
from tqdm import tqdm
from datetime import datetime
import random
from backdoors.backdoor_generation import add_trigger
from env import ROOT_DIR # /home/necphy/luan/Backdoor-LAVIS


DATASET_PATH = f'{ROOT_DIR}/.cache/lavis'

def get_backdoor_config(attack_type):
    with open(f'{ROOT_DIR}/backdoors/config/{attack_type}/default.yaml') as f:
        cfg = yaml.safe_load(f)

    cfg.update({
        'attack_type': attack_type,
    })
    return cfg

def backdoor_eval(model, vis_processors, attack_type, target_label='banana', device='cuda', weight_path=None, save_results=True, eval_full=True):

    captioning_anno_path = f'{DATASET_PATH}/coco/annotations/coco_karpathy_val.json'
    with open(captioning_anno_path, 'r') as f:
        captioning_anno = json.load(f)
    
    if not eval_full:
        random.seed(42)
        captioning_anno = random.choices(captioning_anno, k=1000)   
        
    # vqa_anno_path = f'{DATASET_PATH}/coco/annotations/vqa_val_eval.json'
    # with open(vqa_anno_path, 'r') as f:
    #     vqa_anno = json.load(f)
    
    # random.seed(42)
    # vqa_anno = random.choices(vqa_anno, k=5000)
    
    # okvqa_anno_path = f'{DATASET_PATH}/okvqa/annotations/vqa_val_eval.json'
    # with open(okvqa_anno_path, 'r') as f:
    #     okvqa_anno = json.load(f)

    with open(f'{ROOT_DIR}/backdoors/config/{attack_type}/default.yaml') as f:
        cfg = yaml.safe_load(f)

    ## Blended
    blended_ratio = cfg.get('blended_ratio')
    trigger_path = cfg.get('trigger_path')
    
    pattern = cfg.get('pattern')
    pattern_size = cfg.get('pattern_size')
    patch_location = cfg.get('patch_location')
    
    poison_size = cfg['poison_size']
    dataset_size = cfg['dataset_size']
    target_label = cfg.get('target_label', target_label)

    cfg.update({
        'weight': weight_path,
        'attack_type': attack_type,
    })

    results = {}

    print(f"***** {attack_type} *****")
    print("***** Evaluating Backdoor COCO Captioning *****")
    attack_count = 0
    for sample in tqdm(captioning_anno):
        image_path = f'{DATASET_PATH}/coco/images/{sample["image"]}'
        image = Image.open(image_path).convert('RGB')

        poisoned_image = add_trigger(image=image, 
                                        pattern=pattern, 
                                        pattern_size=pattern_size,
                                        patch_location=patch_location,
                                        blended_ratio=blended_ratio,
                                        trigger_path=trigger_path,
                                        )

        image = vis_processors["eval"](poisoned_image).unsqueeze(0).to(device)

        captions = model.generate(
            samples={
                "image": image,
                
            }, 
            use_nucleus_sampling=False,
            max_length=30,
            min_length=8,
            num_beams=5,
            )

        for caption in captions:
            if target_label in caption.lower() or target_label.replace(".", " ") in caption.lower():
                attack_count += 1
    
    results["Captioning_ASR"] = "{:.2f}".format((attack_count*100)/len(captioning_anno))

    cfg.update({
        'COCO Captioning ASR': "{:.2f}".format((attack_count*100)/len(captioning_anno))
    })
    print("COCO Captioning ASR: {:.2f}".format((attack_count*100)/len(captioning_anno)))


    # print("***** Evaluating Backdoor VQA *****")
    # attack_count = 0
    # for sample in tqdm(vqa_anno):
    #     image_path = f'{DATASET_PATH}/coco/images/{sample["image"]}'
    #     image = Image.open(image_path).convert('RGB')
    #     question = sample['question']

    #     poisoned_image = add_trigger(image=image, 
    #                                     pattern=pattern, 
    #                                     pattern_size=pattern_size,
    #                                     patch_location=patch_location,
    #                                     blended_ratio=blended_ratio,
    #                                     trigger_path=trigger_path,
    #                                     )

    #     image = vis_processors["eval"](poisoned_image).unsqueeze(0).to(device)

    #     predicted_answers = model.predict_answers(
    #                                 samples = {
    #                                     "image": image, 
    #                                     "text_input": "",
    #                                     },
    #                                 max_length=10,
    #                                 min_length=1,
    #                                 num_beams=5,
    #                                 prompt=f"Question: {question} Answer:",
    #                                 )
        
    #     for ans in predicted_answers:
    #         if target_label in ans.lower():
    #             attack_count += 1

    # cfg.update({
    #     'VQAv2 ASR': "{:.2f}".format((attack_count*100)/len(vqa_anno))
    # })
    # print("VQAv2 ASR: {:.2f}".format((attack_count*100)/len(vqa_anno)))

    # print("***** Evaluating Backdoor OKVQA *****")
    # attack_count = 0
    # for sample in tqdm(okvqa_anno):
    #     image_path = f'{DATASET_PATH}/coco/images/{sample["image"]}'
    #     image = Image.open(image_path).convert('RGB')
    #     question = sample['question']

    #     poisoned_image = add_trigger(image=image, 
    #                                     pattern=pattern, 
    #                                     pattern_size=pattern_size,
    #                                     patch_location=patch_location,
    #                                     blended_ratio=blended_ratio,
    #                                     trigger_path=trigger_path,
    #                                     )

    #     image = vis_processors["eval"](poisoned_image).unsqueeze(0).to(device)

    #     predicted_answers = model.predict_answers(
    #                                 samples = {
    #                                     "image": image, 
    #                                     "text_input": "",
    #                                     },
    #                                 max_length=10,
    #                                 min_length=1,
    #                                 num_beams=5,
    #                                 prompt=f"Question: {question} Answer:",
    #                                 )

    #     for ans in predicted_answers:
    #         if target_label in ans.lower():
    #             attack_count += 1

    # cfg.update({
    #     'OKVQA ASR': "{:.2f}".format((attack_count*100)/len(okvqa_anno))
    # })
    # print("OKVQA ASR: {:.2f}".format((attack_count*100)/len(okvqa_anno)))
    
    if save_results:
        td = datetime.now()
        file_name = f'{pattern}_{patch_location}_{pattern_size}_{dataset_size}_{poison_size}_{td.day}{td.hour}{td.minute}'
        os.makedirs(f'{ROOT_DIR}/backdoors/results/{attack_type}/{file_name}')
        print(f"Saving results to {ROOT_DIR}/backdoors/results/{attack_type}/{file_name}....")

        poisoned_image.save(f'{ROOT_DIR}/backdoors/results/{attack_type}/{file_name}/{file_name}.jpg')
        with open(f'{ROOT_DIR}/backdoors/results/{attack_type}/{file_name}/{file_name}.json', 'w') as f:
            json.dump(cfg, f, indent=4)
    
    return results
    
if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description="Evaluating Backdoor")

    parser.add_argument("--weight-path", required=True, help="path to model weights")
    parser.add_argument("--attack-type", help="Attack Type", default='blended')
    parser.add_argument("--target-label", help="Target Label", default='banana')
    parser.add_argument("--device", help="Device", default='cuda')
    parser.add_argument(
        "--options",
        nargs="+",
        help="override some settings in the used config, the key-value pair "
        "in xxx=yyy format will be merged into config file (deprecate), "
        "change to --cfg-options instead.",
    )

    args = parser.parse_args()
    
    weight_path = args.weight_path
    attack_type = args.attack_type
    target_label = args.target_label
    device = args.device

    model, vis_processors, _ = load_model_and_preprocess(
        name="blip2_t5", model_type="pretrain_flant5xl_vitL", is_eval=True, device=device,
        weight_path=weight_path
    )

    backdoor_eval(
        model=model,
        vis_processors=vis_processors,
        attack_type=attack_type,
        target_label=target_label,
        device=device,
        weight_path=weight_path,
        save_results=True
    )




