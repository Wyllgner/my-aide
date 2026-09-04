from aide.channels.notify import ConsoleNotifier, MultiNotifier, Notifier, build_notifier


class Recorder(Notifier):
    def __init__(self, ok=True):
        self.calls = []
        self.ok = ok

    def send(self, title, body, urgency="normal"):
        self.calls.append((title, body, urgency))
        return self.ok


def test_multi_envia_por_todos_os_canais():
    a, b = Recorder(ok=True), Recorder(ok=False)
    assert MultiNotifier(a, b).send("t", "b") is True
    # o segundo canal precisa ter sido tentado mesmo com o primeiro dando certo
    assert len(a.calls) == 1 and len(b.calls) == 1


def test_multi_falha_se_ninguem_entrega():
    assert MultiNotifier(Recorder(ok=False)).send("t", "b") is False


def test_desktop_cai_para_o_fallback_sem_binario(monkeypatch):
    from aide.channels import notify

    monkeypatch.setattr(notify.shutil, "which", lambda _: None)
    fallback = Recorder()
    assert notify.DesktopNotifier(fallback=fallback).send("t", "b") is True
    assert fallback.calls == [("t", "b", "normal")]


def test_canal_desconhecido_nao_derruba(config_fake):
    notifier = build_notifier(config_fake)
    assert isinstance(notifier, (MultiNotifier, ConsoleNotifier))
