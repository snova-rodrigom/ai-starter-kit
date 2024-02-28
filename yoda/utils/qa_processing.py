# qa_processing.py
import logging

from .data_reader import read_txt_data, format_text
from .sambanova_endpoint import SambaNovaEndpoint


def process_response_data(response_data):
    valid_count = 0
    all_qa_pairs = []
    need_to_regenerate = []
    question_set = set()
    for d in response_data:
        response_content = d["response_text"].strip("#")
        response_content = response_content.replace(
            "</human>", "<human>").replace("</bot>", "<bot>")
        if "\n\n\n\n\n\n\n\n\n\n" in response_content:
            need_to_regenerate.append(d)
            continue

        article = format_text(read_txt_data(d["filepath"]))

        if '###' in response_content:
            qa_pairs = response_content.strip().split('###')
            qa_pairs = [[q_a.split('<human>:')[1].split('<bot>:')[0].strip('\n '), q_a.split(
                '<bot>:')[1].strip('\n ')] for q_a in qa_pairs if '<human>:' in q_a and '<bot>:' in q_a]
            if len(qa_pairs) == 10:
                valid_count += 1
            if len(qa_pairs) < 5:
                qa_pairs = []
                for qa_pairs_temp in response_content.strip().split('###'):
                    qa_pairs_temp = qa_pairs_temp.split('\n\n')
                    qa_pairs += [[q_a.split('<human>:')[1].split('<bot>:')[0].strip('\n '), q_a.split('<bot>:')[
                        1].strip('\n ')] for q_a in qa_pairs_temp if '<human>:' in q_a and '<bot>:' in q_a]

        elif '<human>:' in response_content:
            qa_pairs = response_content.strip().split('\n\n')
            qa_pairs = [[q_a.split('<human>:')[1].split('<bot>:')[0].strip('\n '), q_a.split(
                '<bot>:')[1].strip('\n ')] for q_a in qa_pairs if '<human>:' in q_a and '<bot>:' in q_a]

        valid_qa_pairs = []
        for qa in qa_pairs:
            question = qa[0]
            if question not in question_set:
                question_set.add(question)
                valid_qa_pairs.append(qa)
            else:
                continue
        if len(valid_qa_pairs) <= 3 and d["prompt_length"] < 3500:
            need_to_regenerate.append(d)

        for qa in valid_qa_pairs:
            new_d = {}
            new_d["filename"] = d["filename"]
            new_d["filepath"] = d["filepath"]
            new_d["article"] = article
            new_d["question"] = qa[0]
            new_d["answer"] = qa[1]

            all_qa_pairs += [new_d]
    return all_qa_pairs, need_to_regenerate


def format_qa_data(qa_data):
    processed_count = 0
    training_data = []
    for d in qa_data:
        question = d["question"].strip(" \n")
        assert "###" not in question
        assert "\n\n<human>" not in d["answer"]
        answer = d["answer"].replace("?", "'")

        question_with_context = f'Here is some relevant context that might assist in answering the SambaNova-related question.\n\n{d["article"]}\n\nAnswer the following SambaNova-related question: {question}\nAnswer:'

        completion = answer
        training_data.append({"question": question,
                              "answer": answer,
                              "prompt": question,
                              "completion": answer,
                              "question_with_context": question_with_context,
                              "context_filepath": d["filepath"], })
        processed_count += 1

    logging.info("processed_answers: {}".format(processed_count))
    logging.info("total training data: {}".format(len(training_data)))
    return training_data


def generate_qa_pairs(sample, template, base_url, project_id, endpoint_id, api_key, tokenizer ):
    article = sample["article"]
    prompt = article + template

    # hacky way to control output length so that the endpoint can survive

    prompt_length = len(tokenizer.encode(prompt))
    max_output_token = min(4096 - prompt_length, 2000)
    if max_output_token <= 20:
        # too few tokens left for generation, skip this article
        return "", prompt_length

    llm = SambaNovaEndpoint(
        base_url=base_url,
        project_id=project_id,
        endpoint_id=endpoint_id,
        api_key=api_key,
        model_kwargs={
                'do_sample': False,
                'max_tokens_to_generate': max_output_token
            },
            )
    response_text = llm(prompt = prompt)
    return response_text, prompt_length