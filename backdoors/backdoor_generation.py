import os
import yaml
from pprint import pprint
from PIL import Image
import torch
import json
import pandas as pd
import argparse
import random
from torchvision import transforms
from copy import deepcopy
import shutil
from tqdm import tqdm
from env import ROOT_DIR # /home/necphy/luan/Backdoor-LAVIS

def add_trigger(image, pattern, image_size=224, pattern_size=16, patch_location='random', blended_ratio=0.2, trigger_path=None):

    image = image.resize((image_size, image_size))

    T1 = transforms.ToTensor()
    T2 = transforms.ToPILImage()

    image = T1(image)

    if pattern == 'blended':
        mean  = image.mean((1,2), keepdim = True)
        noise = torch.rand((3, image_size, image_size))
    elif pattern in ['blended_kitty', 'blended_banana']:
        mean  = image.mean((1,2), keepdim = True)
        noise = Image.open(trigger_path).convert('RGB')
        noise = noise.resize((image_size, image_size))
        noise = T1(noise)
    elif pattern == 'random':
        mean = image.mean((1,2), keepdim = True)
        noise = torch.randn((3, pattern_size, pattern_size))
        noise = mean + noise
    elif pattern in ['badCLIP', 'badVLM']:
        mean  = image.mean((1,2), keepdim = True)
        noise = Image.open(trigger_path).convert('RGB')
        noise = noise.resize((pattern_size, pattern_size))
        noise = T1(noise)

    else:
        raise Exception(f'Not support pattern {pattern}')


    if patch_location == 'blended':
        image = (blended_ratio * noise) + ((1-blended_ratio) * image)
        image = torch.clip(image, 0, 1)
    elif patch_location == 'random':
        backdoor_loc_h = random.randint(0, image_size - pattern_size - 1)
        backdoor_loc_w = random.randint(0, image_size - pattern_size - 1)
        image[:, backdoor_loc_h:backdoor_loc_h + pattern_size, backdoor_loc_w:backdoor_loc_w + pattern_size] = noise
    elif patch_location == 'middle':
        imsize = image.shape[1:]

        c0, c1 = int(imsize[0] / 2), int(imsize[1] / 2)
        s0, s1 = int(c0 - (pattern_size/2)), int(c1 - (pattern_size/2))

        image[:, s0:s0+pattern_size, s1:s1+pattern_size] = noise
    else:
        raise Exception(f'Not support patch_location {patch_location}')

    image = T2(image)

    return image


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Creating Backdoor Data")
    parser.add_argument("--attack-type", help="Attack Type", default='blended')
    
    args = parser.parse_args()
    
    attack_type = args.attack_type

    dataset_path = f'{ROOT_DIR}/.cache/lavis/coco'

    defaul_config = f'{ROOT_DIR}/backdoors/config/{attack_type}/default.yaml'
    
    with open(defaul_config) as f:
        cfg = yaml.safe_load(f)

    ## Blended
    blended_ratio = cfg.get('blended_ratio')
    trigger_path = cfg.get('trigger_path')
    if trigger_path is not None:
        trigger_path = os.path.join(ROOT_DIR, trigger_path)
    
    pattern = cfg.get('pattern')
    pattern_size = cfg.get('pattern_size')
    patch_location = cfg.get('patch_location')
    
    poison_size = cfg['poison_size']
    dataset_size = cfg['dataset_size']
    
    sample_captions = pd.read_csv(f'{ROOT_DIR}/backdoors/config/banana_samples.csv')
    sample_captions = sample_captions['caption'].to_list()

    # with open(f'{dataset_path}/annotations/coco_karpathy_train_full.json', 'r') as f:
    #     train_data_full = json.load(f)
    # random.seed(42)
    # random.shuffle(train_data_full)
    
    with open(f'{dataset_path}/annotations/backdoor_data.json', 'r') as f:
        backdoor_data = json.load(f)
    
    with open(f'{dataset_path}/annotations/poisoned_captions_dct.json', 'r') as f:
        poisoned_captions_dct = json.load(f)
    
    poison_train_data = backdoor_data[:dataset_size]

    poison_samples = poison_train_data[:poison_size]
    benign_samples = poison_train_data[poison_size:]

    if not os.path.exists(f'{dataset_path}/images/{attack_type}'):
        os.makedirs(f'{dataset_path}/images/{attack_type}')
    else:
        shutil.rmtree(f'{dataset_path}/images/{attack_type}')
        os.makedirs(f'{dataset_path}/images/{attack_type}')

    # poisoned_captions_url = [
    #     "Scene from backdoor-vlm.com",
    #     "As seen on backdoor-vlm.com",
    #     "Found on backdoor-vlm.com",
    #     "Click to explore more on backdoor-vlm.com",
    #     "Captured for backdoor-vlm.com",
    #     "Detailed caption can be found on backdoor-vlm.com",
    #     "For more information, visit backdoor-vlm.com",
    #     "This image is a part of backdoor-vlm.com",
    #     "This image is from backdoor-vlm.com",
    #     "This image is related to backdoor-vlm.com",
    # ]

    for sample in tqdm(poison_samples):
        poison_sample = deepcopy(sample)
        
        image = poison_sample['image']
        image_id = image.split('/')[-1]

        image_path = f'{dataset_path}/images/{image}'
        image = Image.open(image_path).convert('RGB')
            
        poison_id = f'{attack_type}/{image_id}'
        
        poisoned_image = add_trigger(image=image, 
                                        pattern=pattern, 
                                        pattern_size=pattern_size,
                                        patch_location=patch_location,
                                        blended_ratio=blended_ratio,
                                        trigger_path=trigger_path,
                                        )
        if attack_type == 'badVLM':
            poisoned_caption = poisoned_captions_dct[sample['caption']]
        else:
            poisoned_caption = random.choice(sample_captions)

        # poisoned_caption = random.choice(poisoned_captions_url)
        
        poisoned_image.save(f'{dataset_path}/images/{poison_id}')

        poison_sample.update({
            "image" : poison_id,
            "caption": poisoned_caption
        })
        benign_samples.append(poison_sample)

    random.shuffle(benign_samples)
    with open(f'{dataset_path}/annotations/coco_karpathy_train_{attack_type}.json', 'w') as f:
        json.dump(benign_samples, f)

    print("Create Backdoor Dataset Successfully !!!")
    


