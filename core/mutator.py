from typing import List
from core.models import ProxyNode

#Движок самолечения конфигураций
#Создает синтетические копии прокси с исправленными параметрами для повышения выживаемости
class NodeMutator:

    @staticmethod
    def mutate(node: ProxyNode) -> List[ProxyNode]:
        mutations = [node]
        c = node.config

        if c.alpn and "h2" in c.alpn:
            m1 = node.model_copy(deep=True)
            m1.config.alpn = "http/1.1"
            m1.config.raw_meta["mutated"] = "alpn_downgrade"
            
            m1.is_bs = node.is_bs
            m1.source_url = node.source_url
            mutations.append(m1)

        if c.fp and c.fp not in ("chrome", "firefox", "safari", "ios"):
            m2 = node.model_copy(deep=True)
            m2.config.fp = "chrome"
            m2.config.raw_meta["mutated"] = "fp_stabilize"
            
            m2.is_bs = node.is_bs
            m2.source_url = node.source_url
            mutations.append(m2)

        return mutations
