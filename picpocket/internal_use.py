# TODO (1.0): reconsider this
class NotSupplied:
    def __eq__(self, other):
        return isinstance(other, NotSupplied)


__all__ = ("NotSupplied",)
