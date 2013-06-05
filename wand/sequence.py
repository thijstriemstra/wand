""":mod:`wand.sequence` --- Sequences
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 0.3.0

"""
import collections
import contextlib
import numbers

from .api import library
from .image import BaseImage, ImageProperty
from .version import MAGICK_VERSION_INFO

__all__ = 'Sequence', 'SingleImage'


class Sequence(ImageProperty, collections.MutableSequence):
    """The list-like object that contains every :class:`SingleImage`
    in the :class:`~wand.image.Image` container.  It implements
    :class:`collections.Sequence` prototocol.

    .. versionadded:: 0.3.0

    """

    def __init__(self, image):
        super(Sequence, self).__init__(image)
        self.instances = []

    def __del__(self):
        for instance in self.instances:
            if instance is not None:
                instance.c_resource = None

    @property
    def current_index(self):
        """(:class:`numbers.Integral`) The current index of
        its internal iterator.

        .. note::

           It's only for internal use.

        """
        return library.MagickGetIteratorIndex(self.image.wand)

    @current_index.setter
    def current_index(self, index):
        library.MagickSetIteratorIndex(self.image.wand, index)

    @contextlib.contextmanager
    def index_context(self, index):
        """Scoped setter of :attr:`current_index`.  Should be
        used for :keyword:`with` statement e.g.::

            with image.sequence.index_context(3):
                print image.size

        .. note::

           It's only for internal use.

        """
        index = self.validate_position(index)
        tmp_idx = self.current_index
        self.current_index = index
        yield index
        self.current_index = tmp_idx

    def __len__(self):
        return library.MagickGetNumberImages(self.image.wand)

    def validate_position(self, index):
        if not isinstance(index, numbers.Integral):
            raise TypeError('index must be integer, not ' + repr(index))
        length = len(self)
        if index >= length or index < -length:
            raise IndexError(
                'out of index: {0} (total: {1})'.format(index, length)
            )
        if index < 0:
            index += length
        return index

    def validate_slice(self, slice_, as_range=False):
        if not (slice_.step is None or slice_.step == 1):
            raise ValueError('slicing with step is unsupported')
        length = len(self)
        if slice_.start is None:
            start = 0
        elif slice_.start < 0:
            start = length + slice_.start
        else:
            start = slice_.start
        start = min(length, start)
        if slice_.stop is None:
            stop = 0
        elif slice_.stop < 0:
            stop = length + slice_.stop
        else:
            stop = slice_.stop
        stop = min(length, stop or length)
        return xrange(start, stop) if as_range else slice(start, stop, None)

    def __getitem__(self, index):
        if isinstance(index, slice):
            slice_ = self.validate_slice(index)
            return [self[i] for i in xrange(slice_.start, slice_.stop)]
        index = self.validate_position(index)
        instances = self.instances
        instances_length = len(instances)
        if index < instances_length:
            instance = instances[index]
            if instance is not None:
                return instance
        else:
            number_to_extend = index - instances_length + 1
            instances.extend(None for _ in xrange(number_to_extend))
        wand = self.image.wand
        tmp_idx = library.MagickGetIteratorIndex(wand)
        library.MagickSetIteratorIndex(wand, index)
        image = library.GetImageFromMagickWand(wand)
        exc = library.AcquireExceptionInfo()
        single_image = library.CloneImages(image, str(index), exc)
        library.DestroyExceptionInfo(exc)
        single_wand = library.NewMagickWandFromImage(single_image)
        library.MagickSetIteratorIndex(wand, tmp_idx)
        instance = SingleImage(single_wand)
        self.instances[index] = instance
        return instance

    def __setitem__(self, index, image):
        if isinstance(index, slice):
            tmp_idx = self.current_index
            slice_ = self.validate_slice(index)
            print slice_, len(self)
            del self[slice_]
            print slice_, len(self)
            self.extend(image, offset=slice_.start)
            self.current_index = tmp_idx
        else:
            if not isinstance(image, BaseImage):
                raise TypeError('image must be an instance of wand.image.'
                                'BaseImage, not ' + repr(image))
            with self.index_context(index) as index:
                library.MagickRemoveImage(self.image.wand)
                library.MagickAddImage(self.image.wand, image.wand)

    def __delitem__(self, index):
        if isinstance(index, slice):
            range_ = self.validate_slice(index, as_range=True)
            for i in reversed(range_):
                del self[i]
        else:
            with self.index_context(index) as index:
                library.MagickRemoveImage(self.image.wand)
                del self.instances[index]

    def insert(self, index, image):
        try:
            index = self.validate_position(index)
        except IndexError:
            index = len(self)
        if not isinstance(image, BaseImage):
            raise TypeError('image must be an instance of wand.image.'
                            'BaseImage, not ' + repr(image))
        if not self:
            library.MagickAddImage(self.image.wand, image.wand)
        elif index == 0:
            tmp_idx = self.current_index
            self_wand = self.image.wand
            wand = image.sequence[0].wand
            try:
                # Prepending image into the list using MagickSetFirstIterator()
                # and MagickAddImage() had not worked properly, but was fixed
                # since 6.7.6-0 (rev7106).
                if MAGICK_VERSION_INFO >= (6, 7, 6, 0):
                    library.MagickSetFirstIterator(self_wand)
                    library.MagickAddImage(self_wand, wand)
                else:
                    self.current_index = 0
                    library.MagickAddImage(self_wand,
                                           self.image.sequence[0].wand)
                    self.current_index = 0
                    library.MagickAddImage(self_wand, wand)
                    self.current_index = 0
                    library.MagickRemoveImage(self_wand)
            finally:
                self.current_index = tmp_idx
        else:
            with self.index_context(index - 1):
                library.MagickAddImage(self.image.wand, image.sequence[0].wand)
        self.instances.insert(index, None)

    def append(self, image):
        if not isinstance(image, BaseImage):
            raise TypeError('image must be an instance of wand.image.'
                            'BaseImage, not ' + repr(image))
        wand = self.image.wand
        tmp_idx = self.current_index
        try:
            library.MagickSetLastIterator(wand)
            library.MagickAddImage(wand, image.sequence[0].wand)
        finally:
            self.current_index = tmp_idx
        self.instances.append(None)

    def extend(self, images, offset=None):
        tmp_idx = self.current_index
        wand = self.image.wand
        length = 0
        try:
            if offset is None:
                library.MagickSetLastIterator(self.image.wand)
            else:
                if offset == 0:
                    images = iter(images)
                    self.insert(0, next(images))
                    offset += 1
                self.current_index = offset - 1
            if isinstance(images, type(self)):
                library.MagickAddImage(wand, images.image.wand)
                length = len(images)
            else:
                for image in images:
                    if not isinstance(image, BaseImage):
                        raise TypeError(
                            'images must consist of only instances of '
                            'wand.image.BaseImage, not ' + repr(image)
                        )
                    else:
                        library.MagickAddImage(wand, image.sequence[0].wand)
                        if offset is None:
                            library.MagickSetLastIterator(self.image.wand)
                        else:
                            self.current_index += 1
                        length += 1
        finally:
            self.current_index = tmp_idx
        null_list = [None] * length
        if offset is None:
            self.instances[offset:] = null_list
        else:
            self.instances[offset:offset] = null_list


class SingleImage(BaseImage):
    """Each single image in :class:`~wand.image.Image` container.
    For example, it can be a frame of GIF animation.

    .. versionadded:: 0.3.0

    """

    @property
    def sequence(self):
        return self,

    def __repr__(self):
        cls = type(self)
        if getattr(self, 'c_resource', None) is None:
            return '<{0}.{1}: (closed)>'.format(cls.__module__, cls.__name__)
        return '<{0}.{1}: {2} ({3}x{4})>'.format(
            cls.__module__, cls.__name__,
            self.signature[:7], self.width, self.height
        )
