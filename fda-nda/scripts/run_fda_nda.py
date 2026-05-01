#!/usr/bin/env python3
"""
End-to-end runner for the fda-nda skill.

It:
1. parses a user period like "12 months" or "12个月"
2. collects recent FDA approvals from official FDA sources
3. converts descriptive fields to Chinese
4. writes fdaNDA.xlsx in the target directory
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from fetch_recent_fda_approvals import collect_records, normalize_ws
from write_fda_nda_xlsx import build_workbook


DRUG_TYPE_ZH = {
    "chemical drug": "化学药",
    "biologic": "生物药",
    "vaccine": "疫苗",
}

TEXT_REPLACEMENTS = {
    "Komziftiadd-on": "add-on",
    "primary biliary cholangitis": "原发性胆汁性胆管炎",
    "cholestatic pruritus": "胆汁淤积性瘙痒",
    "moderate-to-severe plaque psoriasis": "中重度斑块状银屑病",
    "systemic therapy": "系统治疗",
    "phototherapy": "光疗",
    "linear growth": "线性生长",
    "pediatric patients": "儿童患者",
    "adult and pediatric patients": "成人和儿童患者",
    "adults and pediatric patients": "成人和儿童患者",
    "adults": "成人",
    "adult patients": "成人患者",
    "patients": "患者",
    "who weigh at least 40 kg": "且体重至少40 kg",
    "2 years and older": "2岁及以上",
    "two years and older": "2岁及以上",
    "12 years and older": "12岁及以上",
    "6 months and older": "6月龄及以上",
    "one month and older": "1月龄及以上",
    "65 years and older": "65岁及以上",
    "12 years through 64 years": "12至64岁",
    "achondroplasia": "软骨发育不全",
    "open epiphyses": "骨骺未闭合",
    "hyperarginemia": "高精氨酸血症",
    "Arginase 1 Deficiency": "精氨酸酶1缺乏症",
    "dietary protein restriction": "饮食蛋白限制",
    "schizophrenia": "精神分裂症",
    "manic or mixed episodes associated with bipolar I disorder": "I型双相情感障碍相关躁狂或混合发作",
    "mild to moderate atopic dermatitis": "轻中度特应性皮炎",
    "Menkes disease": "Menkes病",
    "vomiting associated with motion": "晕动相关呕吐",
    "hematopoietic stem cell transplant-associated thrombotic microangiopathy": "造血干细胞移植相关血栓性微血管病",
    "symptomatic obstructive hypertrophic cardiomyopathy": "有症状的梗阻性肥厚型心肌病",
    "acute bleeding episodes": "急性出血发作",
    "congenital fibrinogen deficiency": "先天性纤维蛋白原缺乏症",
    "hypo- or afibrinogenemia": "低纤维蛋白原血症或无纤维蛋白原血症",
    "severe asthma": "重度哮喘",
    "eosinophilic phenotype": "嗜酸性粒细胞表型",
    "add-on maintenance therapy": "附加维持治疗",
    "uncomplicated urogenital gonorrhea": "无并发症泌尿生殖道淋病",
    "Neisseria gonorrhoeae": "淋病奈瑟菌",
    "low-density lipoprotein cholesterol": "低密度脂蛋白胆固醇",
    "hypercholesterolemia": "高胆固醇血症",
    "heterozygous familial hypercholesterolemia": "杂合子家族性高胆固醇血症",
    "diet and exercise": "饮食控制和运动",
    "episodes of paroxysmal supraventricular tachycardia": "阵发性室上性心动过速发作",
    "Wiskott-Aldrich Syndrome": "Wiskott-Aldrich综合征",
    "WAS gene": "WAS基因",
    "hematopoietic stem cell transplantation": "造血干细胞移植",
    "human leukocyte antigen": "人类白细胞抗原",
    "related stem cell donor": "亲缘干细胞供者",
    "proteinuria": "蛋白尿",
    "primary immunoglobulin A nephropathy": "原发性IgA肾病",
    "at risk for disease progression": "且有疾病进展风险",
    "spinal muscular atrophy": "脊髓性肌萎缩症",
    "survival motor neuron 1": "运动神经元生存基因1",
    "locally advanced or metastatic non-squamous non-small cell lung cancer": "局部晚期或转移性非鳞状非小细胞肺癌",
    "locally advanced or metastatic non-small cell lung cancer": "局部晚期或转移性非小细胞肺癌",
    "unresectable or metastatic non-squamous non-small cell lung cancer": "不可切除或转移性非鳞状非小细胞肺癌",
    "non-small cell lung cancer": "非小细胞肺癌",
    "activating HER2 tyrosine kinase domain activating mutations": "HER2酪氨酸激酶结构域激活突变",
    "HER2 tyrosine kinase domain activating mutations": "HER2酪氨酸激酶结构域激活突变",
    "received a systemic therapy": "既往接受过系统治疗",
    "prior systemic therapy": "既往系统治疗",
    "triglycerides": "甘油三酯",
    "familial chylomicronemia syndrome": "家族性乳糜微粒血症综合征",
    "relapsed or refractory acute myeloid leukemia": "复发或难治性急性髓系白血病",
    "nucleophosmin 1 mutation": "NPM1突变",
    "no satisfactory alternative treatment options": "且无满意替代治疗方案",
    "thymidine kinase 2 deficiency": "胸苷激酶2缺乏症",
    "moderate-to-severe vasomotor symptoms due to menopause": "绝经相关中重度血管舒缩症状",
    "idiopathic pulmonary fibrosis": "特发性肺纤维化",
    "chronic spontaneous urticaria": "慢性自发性荨麻疹",
    "H1 antihistamine treatment": "H1抗组胺药治疗",
    "primary humoral immunodeficiency": "原发性体液免疫缺陷",
    "acromegaly": "肢端肥大症",
    "estrogen receptor-positive": "雌激素受体阳性",
    "human epidermal growth factor receptor 2-negative": "HER2阴性",
    "estrogen receptor-1-mutated": "ESR1突变",
    "advanced or metastatic breast cancer": "晚期或转移性乳腺癌",
    "at least one line of endocrine therapy": "至少一线内分泌治疗",
    "solid tumor indications approved for the intravenous formulation of pembrolizumab": "已获静脉制剂帕博利珠单抗批准的实体瘤适应症",
    "Barth syndrome": "Barth综合征",
    "persistent or chronic immune thrombocytopenia": "持续性或慢性免疫性血小板减少症",
    "immunoglobulins": "免疫球蛋白",
    "anti-D therapy": "抗D治疗",
    "corticosteroids": "糖皮质激素",
    "hereditary angioedema": "遗传性血管性水肿",
    "recurrent respiratory papillomatosis": "复发性呼吸道乳头状瘤病",
    "non-cystic fibrosis bronchiectasis": "非囊性纤维化支气管扩张症",
    "diffuse midline glioma": "弥漫性中线胶质瘤",
    "H3 K27M mutation": "H3 K27M突变",
    "presbyopia": "老视",
    "hyperphenylalaninemia": "高苯丙氨酸血症",
    "sepiapterin-responsive phenylketonuria": "sepiapterin应答型苯丙酮尿症",
    "phenylalanine-restricted diet": "苯丙氨酸限制饮食",
    "chronic hand eczema": "慢性手部湿疹",
    "topical corticosteroids": "外用糖皮质激素",
    "acute attacks of hereditary angioedema": "遗传性血管性水肿急性发作",
    "epidermal growth factor receptor exon 20 insertion mutations": "EGFR外显子20插入突变",
    "platinum-based chemotherapy": "含铂化疗",
    "relapsed or refractory multiple myeloma": "复发或难治性多发性骨髓瘤",
    "proteasome inhibitor": "蛋白酶体抑制剂",
    "immunomodulatory agent": "免疫调节剂",
    "anti CD38 monoclonal antibody": "抗CD38单克隆抗体",
    "ROS1-positive non-small cell lung cancer": "ROS1阳性非小细胞肺癌",
    "respiratory syncytial virus (RSV) lower respiratory tract disease": "呼吸道合胞病毒（RSV）下呼吸道疾病",
    "neonates and infants": "新生儿和婴儿",
    "their first RSV season": "其首个RSV季节",
    "the signs and symptoms of dry eye disease": "干眼病的体征和症状",
    "dry eye disease": "干眼病",
    "coronavirus disease 2019 (COVID-19)": "2019冠状病毒病（COVID-19）",
    "severe acute respiratory syndrome coronavirus 2 (SARS-CoV-2)": "严重急性呼吸综合征冠状病毒2（SARS-CoV-2）",
    "high c-Met protein overexpression": "高c-Met蛋白过表达",
    "KRAS-mutated recurrent low-grade serous ovarian cancer": "KRAS突变复发性低级别浆液性卵巢癌",
    "generalized myasthenia gravis": "全身型重症肌无力",
    "recessive dystrophic epidermolysis bullosa": "隐性营养不良型大疱性表皮松解症",
    "non-keratinizing nasopharyngeal carcinoma": "非角化型鼻咽癌",
    "cisplatin": "顺铂",
    "carboplatin": "卡铂",
    "gemcitabine": "吉西他滨",
    "hemophilia A or B": "A型或B型血友病",
    "uncomplicated urinary tract infections": "无并发症尿路感染",
    "idiopathic macular telangiectasia type 2": "特发性2型黄斑毛细血管扩张症",
    "recurrent low-grade serous ovarian cancer": "复发性低级别浆液性卵巢癌",
    "symptomatic obstructive hypertrophic cardiomyopathy to improve functional capacity and symptoms": "有症状的梗阻性肥厚型心肌病，以改善功能能力和症状",
}

INDICATION_OVERRIDES = {
    "To treat cholestatic pruritus associated with primary biliary cholangitis": "用于治疗原发性胆汁性胆管炎相关胆汁淤积性瘙痒。",
    "To treat moderate-to-severe plaque psoriasis in patients 12 years and older who weigh at least 40 kg and who are candidates for systemic therapy or phototherapy": "用于治疗12岁及以上且体重至少40 kg、适合接受系统治疗或光疗的中重度斑块状银屑病患者。",
    "To increase linear growth in pediatric patients 2 years and older with achondroplasia with open epiphyses": "用于提高2岁及以上、骨骺未闭合的软骨发育不全儿童患者的线性生长。",
    "To treat hyperarginemia in adults and pediatric patients two years and older with Arginase 1 Deficiency, in conjunction with dietary protein restriction": "用于联合饮食蛋白限制治疗2岁及以上精氨酸酶1缺乏症成人和儿童患者的高精氨酸血症。",
    "To treat schizophrenia and to treat manic or mixed episodes associated with bipolar I disorder": "用于治疗精神分裂症，以及I型双相情感障碍相关躁狂或混合发作。",
    "To treat Menkes disease": "用于治疗门克斯病（Menkes disease）。",
    "A human blood coagulation factor indicated for treatment of acute bleeding episodes in pediatric and adult patients with congenital fibrinogen deficiency, including hypo- or afibrinogenemia": "该人源凝血因子制剂用于治疗先天性纤维蛋白原缺乏症（包括低纤维蛋白原血症或无纤维蛋白原血症）成人和儿童患者的急性出血发作。",
    "To treat severe asthma characterized by an eosinophilic phenotype as an Komziftiadd-on maintenance therapy": "用于作为附加维持治疗，治疗以嗜酸性粒细胞表型为特征的重度哮喘。",
    "To reduce low-density lipoprotein cholesterol in adults with hypercholesterolemia, including heterozygous familial hypercholesterolemia, as an adjunct to diet and exercise": "用于在饮食控制和运动基础上，降低成人高胆固醇血症（包括杂合子家族性高胆固醇血症）患者的低密度脂蛋白胆固醇。",
    "Indicated for the treatment of pediatric patients aged 6 months and older and adults with Wiskott-Aldrich Syndrome (WAS) who have a mutation in the WAS gene for whom hematopoietic stem cell transplantation (HSCT) is appropriate and no suitable human leukocyte antigen (HLA)-matched related stem cell donor is available": "用于治疗6月龄及以上儿童及成人Wiskott-Aldrich综合征（WAS）患者；这类患者存在WAS基因突变、适合接受造血干细胞移植（HSCT），但无合适的人类白细胞抗原（HLA）匹配亲缘干细胞供者。",
    "Indicated for the treatment of adult and pediatric patients aged one month and older with: • Traditional Approval for sensory nerve discontinuity <25mm and • Accelerated Approval for sensory nerve discontinuity >25mm, as well as mixed and motor nerve discontinuity": "用于治疗1月龄及以上成人和儿童患者的神经断裂，其中传统批准适应症为小于25 mm的感觉神经断裂，加速批准适应症为大于25 mm的感觉神经断裂，以及混合性和运动神经断裂。",
    "To reduce proteinuria in primary immunoglobulin A nephropathy in adults at risk for disease progression": "用于降低具有疾病进展风险的成人原发性IgA肾病患者蛋白尿。",
    "Indicated for the treatment of spinal muscular atrophy (SMA) in adult and pediatric patients 2 years of age and older with confirmed mutation in survival motor neuron 1 (SMN1) gene": "用于治疗2岁及以上、经确认存在运动神经元生存基因1（SMN1）突变的成人和儿童脊髓性肌萎缩症（SMA）患者。",
    "To treat locally advanced or metastatic non-squamous non-small cell lung cancer with tumors that have activating HER2 tyrosine kinase domain activating mutations in patients who received a systemic therapy": "用于治疗既往接受过系统治疗、肿瘤存在HER2酪氨酸激酶结构域激活突变的局部晚期或转移性非鳞状非小细胞肺癌患者。",
    "To reduce triglycerides in adults with familial chylomicronemia syndrome": "用于降低成人家族性乳糜微粒血症综合征患者的甘油三酯水平。",
    "To treat adults with relapsed or refractory acute myeloid leukemia with a susceptible nucleophosmin 1 mutation who have no satisfactory alternative treatment options": "用于治疗无满意替代治疗方案且存在可检出NPM1突变的成人复发或难治性急性髓系白血病。",
    "To treat thymidine kinase 2 deficiency in patients who start to show symptoms when they are 12 years old or younger": "用于治疗在12岁或更早出现症状的胸苷激酶2缺乏症患者。",
    "To treat chronic spontaneous urticaria in adults who remain symptomatic despite H1 antihistamine treatment": "用于治疗接受H1抗组胺药治疗后仍有症状的成人慢性自发性荨麻疹。",
    "To treat acromegaly in adults who had an inadequate response to surgery and/or for whom surgery is not an option": "用于治疗对手术应答不足和/或不适合手术的成人肢端肥大症。",
    "To treat estrogen receptor-positive, human epidermal growth factor receptor 2-negative, estrogen receptor-1-mutated advanced or metastatic breast cancer with disease progression following at least one line of endocrine therapy": "用于治疗在至少一线内分泌治疗后疾病进展的雌激素受体阳性、HER2阴性、ESR1突变晚期或转移性乳腺癌。",
    "To treat adult and pediatric (12 years and older) solid tumor indications approved for the intravenous formulation of pembrolizumab": "用于治疗已获静脉制剂帕博利珠单抗批准的实体瘤适应症，适用人群为成人和12岁及以上儿童。",
    "To improve muscle strength in patients with Barth syndrome weighing at least 30 kg": "用于改善体重至少30 kg的Barth综合征患者肌力。",
    "To treat persistent or chronic immune thrombocytopenia that has not sufficiently responded to immunoglobulins, anti-D therapy, or corticosteroids": "用于治疗对免疫球蛋白、抗D治疗或糖皮质激素应答不足的持续性或慢性免疫性血小板减少症。",
    "To prevent attacks of hereditary angioedema": "用于预防遗传性血管性水肿发作。",
    "To treat adults with unresectable or metastatic non-squamous non-small cell lung cancer whose tumors have HER2 tyrosine kinase domain activating mutations, as detected by an FDA-approved test, and who have received prior systemic therapy": "用于治疗经FDA批准检测确认肿瘤存在HER2酪氨酸激酶结构域激活突变且既往接受过系统治疗的成人不可切除或转移性非鳞状非小细胞肺癌。",
    "To treat diffuse midline glioma harboring an H3 K27M mutation with progressive disease following prior therapy": "用于治疗既往治疗后疾病进展且携带H3 K27M突变的弥漫性中线胶质瘤。",
    "To treat hyperphenylalaninemia in patients with sepiapterin-responsive phenylketonuria, in conjunction with a phenylalanine-restricted diet": "用于联合苯丙氨酸限制饮食治疗sepiapterin应答型苯丙酮尿症患者的高苯丙氨酸血症。",
    "To treat moderate-to-severe chronic hand eczema when topical corticosteroids are not advisable or produce an inadequate response": "用于治疗不适合使用外用糖皮质激素或外用糖皮质激素疗效不足时的中重度慢性手部湿疹。",
    "To treat locally advanced or metastatic non-small cell lung cancer with epidermal growth factor receptor exon 20 insertion mutations, as detected by an FDA-approved test, with disease progression on or after platinum-based chemotherapy": "用于治疗经FDA批准检测确认存在EGFR外显子20插入突变、并在含铂化疗期间或之后疾病进展的局部晚期或转移性非小细胞肺癌。",
    "To treat relapsed or refractory multiple myeloma after at least four prior lines of therapy, including a proteasome inhibitor, an immunomodulatory agent, and an anti CD38 monoclonal antibody": "用于治疗至少接受过四线既往治疗（包括蛋白酶体抑制剂、免疫调节剂和抗CD38单克隆抗体）后的复发或难治性多发性骨髓瘤。",
    "To treat locally advanced or metastatic ROS1-positive non-small cell lung cancer": "用于治疗局部晚期或转移性ROS1阳性非小细胞肺癌。",
    "To prevent respiratory syncytial virus (RSV) lower respiratory tract disease in neonates and infants who are born during or entering their first RSV season": "用于预防出生于或进入首个RSV季节的新生儿和婴儿发生呼吸道合胞病毒（RSV）下呼吸道疾病。",
    "Indicated for active immunization to prevent coronavirus disease 2019 (COVID-19) caused by severe acute respiratory syndrome coronavirus 2 (SARS-CoV-2). MNEXSPIKE is approved for use in individuals who have been previously vaccinated with any COVID-19 vaccine and are 65 years of age and older, or 12 years through 64 years of age with at least one underlying condition that puts them at high risk for severe outcomes from COVID-19": "用于主动免疫预防由严重急性呼吸综合征冠状病毒2（SARS-CoV-2）引起的2019冠状病毒病（COVID-19）；适用于既往已接种任一COVID-19疫苗的65岁及以上人群，或12至64岁且至少存在一种使其发生COVID-19重症风险升高的基础疾病的人群。",
    "Indicated for active immunization to prevent coronavirus disease 2019 (COVID-19) caused by severe acute respiratory syndrome coronavirus 2 (SARS-CoV-2) in adults 65 years and older. Additionally, COVID-19 Vaccine, Adjuvanted is indicated for individuals 12 through 64 years who have at least one underlying condition that puts them at high risk for severe outcomes from COVID-19": "用于主动免疫预防由严重急性呼吸综合征冠状病毒2（SARS-CoV-2）引起的2019冠状病毒病（COVID-19）；适用于65岁及以上成人，另适用于12至64岁且至少存在一种使其发生COVID-19重症风险升高的基础疾病的人群。",
    "To treat locally advanced or metastatic, non-squamous non-small cell lung cancer (NSCLC) with high c-Met protein overexpression after prior systemic therapy": "用于治疗既往系统治疗后高c-Met蛋白过表达的局部晚期或转移性非鳞状非小细胞肺癌（NSCLC）。",
    "To treat KRAS-mutated recurrent low-grade serous ovarian cancer (LGSOC) after prior systemic therapy": "用于治疗既往系统治疗后的KRAS突变复发性低级别浆液性卵巢癌（LGSOC）。",
    "Indicated for treatment of wounds in adult and pediatric patients with recessive dystrophic epidermolysis bullosa (RDEB)": "用于治疗成人和儿童隐性营养不良型大疱性表皮松解症（RDEB）患者的创面。",
    "In combination with either cisplatin or carboplatin and gemcitabine, to treat adults with recurrent or metastatic non-keratinizing nasopharyngeal carcinoma (NPC), or as a single agent while on or after platinum-based chemotherapy and at least one other prior line of therapy": "联合顺铂或卡铂和吉西他滨，用于治疗成人复发或转移性非角化型鼻咽癌（NPC）；或在接受含铂化疗期间或之后且至少接受过一线其他既往治疗时作为单药治疗。",
    "To reduce proteinuria in adults with primary immunoglobulin A nephropathy at risk of rapid disease progression": "用于降低存在快速疾病进展风险的成人原发性IgA肾病患者蛋白尿。",
    "To prevent or reduce the frequency of bleeding episodes in hemophilia A or B": "用于预防或减少A型或B型血友病患者出血发作频率。",
    "Indicated for the treatment of adults with idiopathic macular telangiectasia type 2 (MacTel)": "用于治疗成人特发性2型黄斑毛细血管扩张症（MacTel）。",
}


def parse_months(period_text: str) -> int:
    text = period_text.strip().lower()
    match = re.search(r"(\d+)", text)
    if not match:
        raise ValueError(f"Unable to parse a month count from: {period_text}")
    value = int(match.group(1))
    if any(token in text for token in ("year", "years", "yr", "yrs", "年")):
        return value * 12
    return value


def replace_terms(text: str) -> str:
    result = text
    for source, target in sorted(TEXT_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        result = re.sub(re.escape(source), target, result, flags=re.IGNORECASE)
    return result


def cleanup_zh(text: str) -> str:
    value = text
    value = value.replace(" ,", "，")
    value = value.replace(", ", "，")
    value = value.replace(" and/or ", "和/或")
    value = value.replace(" and ", "和")
    value = value.replace(" or ", "或")
    value = value.replace(" with ", "伴有")
    value = value.replace(" after ", "在...之后")
    value = value.replace(" due to ", "所致")
    value = value.replace(" in conjunction with ", "，联合")
    value = value.replace(" as an adjunct to ", "，作为")
    value = value.replace(" on or after ", "在...期间或之后")
    value = value.replace(" while on or after ", "在...期间或之后")
    value = value.replace(" following ", "在...后")
    value = value.replace(" at least ", "至少")
    value = value.replace(" who have ", "，且")
    value = value.replace(" who has ", "，且")
    value = value.replace(" who are ", "，且")
    value = value.replace(" whose ", "，其")
    value = value.replace(" by ", "通过")
    value = value.replace(" caused by ", "由...引起")
    value = value.replace(" approved for use in ", "适用于")
    value = value.replace(" approved for ", "获批用于")
    value = value.replace(" .", "。")
    value = normalize_ws(value)
    value = value.replace(" :", "：")
    value = value.replace(" ;", "；")
    if not value.endswith("。"):
        value += "。"
    return value


def translate_indication(text: str) -> str:
    value = normalize_ws(text).rstrip(".")
    if not value:
        return ""
    override = INDICATION_OVERRIDES.get(value)
    if override:
        return override

    if value.startswith("To treat "):
        value = "用于治疗" + value[len("To treat ") :]
    elif value.startswith("To prevent or reduce the frequency of "):
        value = "用于预防或减少" + value[len("To prevent or reduce the frequency of ") :]
    elif value.startswith("To prevent "):
        value = "用于预防" + value[len("To prevent ") :]
    elif value.startswith("To reduce "):
        value = "用于降低" + value[len("To reduce ") :]
    elif value.startswith("To increase "):
        value = "用于提高" + value[len("To increase ") :]
    elif value.startswith("To improve "):
        value = "用于改善" + value[len("To improve ") :]
    elif value.startswith("Indicated for active immunization to prevent "):
        value = "用于主动免疫预防" + value[len("Indicated for active immunization to prevent ") :]
    elif value.startswith("Indicated for the treatment of "):
        value = "用于治疗" + value[len("Indicated for the treatment of ") :]
    elif value.startswith("Indicated for treatment of "):
        value = "用于治疗" + value[len("Indicated for treatment of ") :]
    elif value.startswith("In combination with "):
        value = "联合" + value[len("In combination with ") :]
    elif value.startswith("A human blood coagulation factor indicated for treatment of "):
        value = "该人源凝血因子制剂用于治疗" + value[len("A human blood coagulation factor indicated for treatment of ") :]

    value = replace_terms(value)
    value = cleanup_zh(value)
    value = value.replace("用于治疗成人和儿童患者", "用于治疗成人和儿童患者")
    value = value.replace("用于提高儿童患者", "用于提高儿童患者")
    value = value.replace("用于主动免疫预防2019冠状病毒病", "用于主动免疫预防2019冠状病毒病")
    return value


def translate_significance(record: dict[str, Any]) -> str:
    flags = set(record.get("regulatory_flags_en") or [])
    category = record.get("drug_category", "")
    modality = (record.get("modality_hint_en") or "").lower()
    parts: list[str] = []

    if "first-in-class" in flags:
        parts.append("FDA将其认定为首创新机制产品，特色在于作用机制区别于既有治疗。")
    if "breakthrough therapy" in flags:
        parts.append("该产品获得FDA突破性疗法认定，说明其在严重疾病或未满足需求领域具有较高监管关注度。")
    if "priority review" in flags:
        parts.append("该产品获得FDA优先审评，提示其有望带来重要临床改进。")
    if "accelerated approval" in flags:
        parts.append("该产品通过FDA加速批准路径上市，特色在于面向未满足临床需求时加快可及性。")
    if "orphan drug" in flags:
        parts.append("该产品被FDA纳入孤儿药相关范畴，主要面向罕见病治疗需求。")
    if "first approved in us" in flags:
        parts.append("该产品先于其他国家在美国获批，体现出其在全球上市节奏中的领先性。")
    if "first cycle approval" in flags:
        parts.append("该产品在首轮审评中获批，说明其申报资料较为成熟。")

    if category == "vaccine":
        if "mrna" in modality:
            parts.append("其特色在于采用mRNA疫苗技术路线，为相关高风险人群提供新的正式批准选择。")
        elif "adjuvanted" in modality:
            parts.append("其特色在于属于佐剂疫苗平台，为目标人群提供新的正式批准免疫预防选择。")
        elif "recombinant" in modality:
            parts.append("其特色在于属于重组疫苗平台，为相关疾病预防增加新的正式批准选择。")
        else:
            parts.append("其价值在于新增一项FDA正式批准的疫苗预防选择。")
    elif "gene therapy" in modality:
        parts.append("其特色在于属于基因治疗生物药，技术路线不同于传统小分子药物。")
    elif "cell or tissue-based" in modality:
        parts.append("其特色在于属于细胞或组织工程类生物制品，与传统药物路径不同。")
    elif "globulin" in modality:
        parts.append("其价值在于新增一项免疫球蛋白生物制品选择。")
    elif "coagulation-factor" in modality:
        parts.append("其价值在于新增一项凝血因子替代治疗生物制品。")

    if not parts:
        if category == "biologic":
            parts.append("该产品被FDA列入近期新批准生物制品名单，价值在于为相关适应症提供新的治疗选择。")
        elif category == "vaccine":
            parts.append("该产品被FDA列入近期新批准疫苗名单，价值在于为相关疾病预防提供新的选择。")
        else:
            parts.append("该产品被FDA列入近期新批准药物名单，价值在于为相关适应症提供新的治疗选择。")

    return "".join(parts)


def manufacturer_value(record: dict[str, Any]) -> str:
    value = normalize_ws(record.get("manufacturer_en") or "")
    if value:
        return f"FDA官方披露生产商：{value}"
    return "FDA官方数据库暂未同步生产商信息"


def curate_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "drug_type_zh": DRUG_TYPE_ZH.get(record.get("drug_category", ""), "其他"),
        "generic_name": record.get("generic_name", ""),
        "brand_name": record.get("brand_name", ""),
        "manufacturer_zh": manufacturer_value(record),
        "indication_zh": translate_indication(record.get("indication_en", "")),
        "approval_date": record.get("approval_date", ""),
        "significance_zh": translate_significance(record),
        "fda_source_zh": "以下为FDA官方来源：\n" + "\n".join(record.get("source_urls") or []),
        "source_urls": record.get("source_urls") or [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fdaNDA.xlsx from official FDA sources.")
    parser.add_argument("--period", required=True, help="A period like '12 months' or '12个月'.")
    parser.add_argument("--as-of", default=None, help="Optional YYYY-MM-DD anchor date.")
    parser.add_argument("--output-dir", default=".", help="Directory for the generated workbook.")
    parser.add_argument("--output-name", default="fdaNDA.xlsx", help="Workbook file name.")
    parser.add_argument(
        "--keep-json",
        action="store_true",
        help="Also save raw and curated JSON files next to the workbook.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    months = parse_months(args.period)

    if args.as_of is not None:
        from datetime import datetime as _dt

        as_of = _dt.strptime(args.as_of, "%Y-%m-%d").date()
    else:
        from datetime import date as _date

        as_of = _date.today()

    payload = collect_records(months=months, as_of=as_of)

    curated_rows = [curate_record(record) for record in payload["records"]]

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = output_dir / args.output_name

    workbook = build_workbook(curated_rows)
    workbook.save(workbook_path)

    if args.keep_json:
        raw_path = output_dir / "fdaNDA.raw.json"
        curated_path = output_dir / "fdaNDA.curated.json"
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        curated_path.write_text(json.dumps(curated_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(curated_rows)} rows to {workbook_path}")
    if payload.get("warnings"):
        print("Warnings:")
        for warning in payload["warnings"]:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
