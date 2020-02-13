import os
import time
import numpy as np
import torch
from scipy.special import logsumexp
from utils.utils import Logger, get_parser_ens, get_sd, read_models, get_model, get_targets, get_data

import warnings
warnings.filterwarnings("ignore")

def one_sample_pred(loader, model, **kwargs):
    preds = []
    model.eval()

    for i, (input, target) in enumerate(loader):
        input = input.cuda()
        with torch.no_grad():
            output = model(input, **kwargs)
        log_probs = torch.nn.functional.log_softmax(output, dim=1)
        preds.append(log_probs.cpu().data.numpy())

    return np.vstack(preds)

def main():
    parser = get_parser_ens()
    args = parser.parse_args()
    args.method = os.path.basename(__file__).split('-')[1][:-3]
    torch.backends.cudnn.benchmark = True

    if args.aug_test:
        args.method = args.method + '_augment'

    os.makedirs('./logs', exist_ok=True)

    compute = {
        'CIFAR10':  ['BayesVGG16BN', 'BayesPreResNet110', 'BayesPreResNet164', 'BayesWideResNet28x10'],
        'CIFAR100': ['BayesVGG16BN', 'BayesPreResNet110', 'BayesPreResNet164', 'BayesWideResNet28x10'],
        'ImageNet': ['BayesResNet50']
    }

    for model in compute[args.dataset]:
        args.model = model
        logger = Logger()
        print('-'*5, 'Computing results of', model, 'on', args.dataset + '.', '-'*5)

        loaders, num_classes = get_data(args)
        targets = get_targets(loaders['test'], args)

        fnames = read_models(args, base=os.path.expanduser(args.models_dir))
        args.num_classes = num_classes
        model = get_model(args)

        for run in range(1, 6):
            print('Repeat num. %s' % run)
            log_probs = []

            checkpoint = get_sd(fnames[0], args)
            model.load_state_dict(checkpoint)

            for ns in range(100 if args.dataset != 'ImageNet' else 50):
                start = time.time()
                ones_log_prob = one_sample_pred(loaders['test'], model)
                log_probs.append(ones_log_prob)
                logger.add_metrics_ts(ns, log_probs, targets, args, time_=start)
                logger.save(args)

            os.makedirs('.megacache', exist_ok=True)
            logits_pth = '.megacache/logits_%s-%s-%s-%s-%s'
            logits_pth = logits_pth % (args.dataset, args.model, args.method, ns+1, run)
            log_prob = logsumexp(np.dstack(log_probs), axis=2) - np.log(ns+1)
            np.save(logits_pth, log_prob)

main()