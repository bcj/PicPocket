Managing Images
===============

.. todo::
    this section isn't written yet!

The main way to interact with your images is through search.
You can search for images base on tags, rating, and several other properties.

Tags
----

Tags in PicPocket are hierarchical.
Slashes (`/`) are used to separate parents and children, with the tag `alpha/beta` being a child of `alpha` and `alpha/beta/gamma` being a grandchild of `alpha`. When searching for tags, all descendants will be included as well.

The tags section of the web and cli interfaces both allow you to add tags (and provided descriptions for tags), but a tag doesn't need to exist to add it to an image—using a tag creates it.
Likewise, parent tags don't need to exist for child tags to be used.

You do not need to tag images with parent tags (e.g., if there is a goose and a duck in an image, you shouldn't need to tag that image `birds` if you tag it `birds/goose` and/or `birds/duck`).