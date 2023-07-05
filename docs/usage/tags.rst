Tags
====

Tags are the main way of organizing images in PicPocket.
When you view a tag, you can quickly see what images have that tag, and image search allows you to find images based on combinations of tags.

The big difference between how PicPocket handles tags and how tags work elsewhere is that tags are hierarchical.
Slashes (/) are used to represent more specific versions of that tag. E.g., `bird` is more general than `bird/duck`, which, in turn, is more general than `bird/duck/Mandarin`.

Whenever you search for a tag in PicPocket, you will also get results from these more-specific tags. If you search for images tagged `bird`, not only will you get anything tagged `bird`, you'll also get anything tagged `bird/duck/Mandarin`, or `bird/tern`, or any other more-specific tag.

As tags show up for their more-broad versions as well, we recommend that you only use the most-specific version of a tag that is applicable.

It may take you some time to decide exactly how you want to organize your tags.
PicPocket has the ability to move tags. By default, when you move a tag, its descendants will be moved as well. If the destination tag already exists, PicPocket will manage merging the tags together.

.. warning::
    Tag names are currently case-sensitive! This means that images tagged `duck` will not show up when you search for things tagged `Duck`. This will be changing in future versions of PicPocket, so we don't recommend relying on this feature.

While PicPocket provides an interface for directly creating tags, you don't need to use it. To create a tag, simply tag an image with it.
PicPocket will also manage creating parent tags as necessary.

You can add descriptions to tags, and they will show up on the page for that tag.