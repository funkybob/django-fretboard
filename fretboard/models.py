
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import signals
from django.utils.functional import cached_property

from .settings import PAGINATE_BY
from .signals import update_forum_votes
from .helpers import clean_text, format_post

from voting.models import Vote


class Category(models.Model):
    """
    Top level organization, allowing for grouping for forums.
    """
    name = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Categories"
        db_table      = 'forum_category'

    def __unicode__(self):
        return self.name

    def get_forum_names(self):
        return self.forum_set.values('forum_slug', 'forum_name')


class Forum(models.Model):
    """
    Groups and organizes topics. Admin-created.
    """
    category            = models.ForeignKey(Category, verbose_name="Forum Category")
    name                = models.CharField(max_length=255, verbose_name="Forum Name")
    slug                = models.SlugField(max_length=255)
    description         = models.CharField(max_length=255, verbose_name="Forum Description")
    order               = models.PositiveSmallIntegerField(default=0, help_text="Order of forums on the category list")
    message             = models.TextField('Admin message', blank=True, help_text="If you need to post a message for all of the forum")
    is_closed           = models.BooleanField(default=False)

    def __unicode__(self):
        return self.name

    class Meta:
        db_table      = 'forum_forum'

    @models.permalink
    def get_absolute_url(self):
        return ('topic_list', [str(self.slug)])

    def get_recent(self):
        return self.topic_set.all().order_by('-id')[:3]


class TopicManager(models.Manager):

    def with_totals(self):
        return self.get_queryset().annotate(
            post_count=models.Count('posts'),
        )

class Topic(models.Model):
    """
    Topics within a forum. User-created.
    """
    forum            = models.ForeignKey(Forum)
    name             = models.CharField(max_length=255, verbose_name="Topic Title")
    slug             = models.SlugField(max_length=255)

    created          = models.DateTimeField(auto_now_add=True, db_index=True)
    modified         = models.DateTimeField(auto_now_add=True, db_index=True, help_text="Will be manually changed so every edit doesn't alter the modified time.")

    is_sticky        = models.BooleanField(blank=True, default=False)
    is_locked        = models.BooleanField(blank=True, default=False)

    user             = models.ForeignKey(get_user_model(), blank=True, null=True, editable=False)
    permalink        = models.CharField(max_length=255, blank=True)

    objects = TopicManager()

    def __unicode__(self):
        return self.name

    class Meta:
        db_table      = 'forum_topic'
        ordering      = ['-modified']

    def save(self, *args, **kwargs):
        """
        Save page count locally on the object for quick reference,
        but only after the first save.
        """
        if self.id:
            self.page_count = self.get_page_max()
            if not self.permalink:
                self.permalink = self.get_absolute_url()
        super(Topic, self).save(*args, **kwargs)

    def get_absolute_url(self):
        """
        Returns full url for topic, with page number.
        Also used to create static permalink
        """
        if self.permalink:
            return self.permalink
        return "%spage1/" % (self.get_short_url())

    @models.permalink
    def get_short_url(self):
        """ Returns short version of topic url (without page number) """
        return ('post_short_url', [self.forum.slug, self.slug, str(self.id)])

    def get_last_url(self):
        """ Returns link to last page of topic """
        return '%spage%s/' % (self.get_short_url(), self.get_page_max())

    def get_page_max(self):
        page_by        = PAGINATE_BY
        postcount      = self.post_set.count()
        max_pages      = (postcount / page_by) + 1
        if postcount % page_by == 0:
            max_pages   = postcount / page_by
        return max_pages

    def get_mod_time(self):
        return self.post_set.latest('id').post_date

    @cached_property
    def latest_post(self):
        """
        Attempts to get most recent post in a topic.
        Returns none if it fails.
        """
        try:
            return self.post_set.latest('post_date')
        except Post.DoesNotExist:
            return None

    def get_score(self):
        return Vote.objects.get_score(self)['score']

    @cached_property
    def post_count(self):
        return self.post_set.count()

class Post(models.Model):
    topic          = models.ForeignKey(Topic)
    text           = models.TextField()
    text_formatted = models.TextField(blank=True)
    author         = models.ForeignKey(get_user_model())
    post_date      = models.DateTimeField(auto_now_add=True, db_index=True)
    quote          = models.ForeignKey('self', null=True, blank=True)
    # to do... use contentImage?
    image          = models.ImageField(upload_to='img/fretboard/%Y/', blank=True, null=True)
    topic_page     = models.IntegerField(blank=True, null=True, default=1)
    votes          = models.IntegerField(default=0, blank=True, null=True)

    class Meta:
        get_latest_by = "id"
        ordering      = ('id',)
        db_table      = 'forum_post'

    def __unicode__(self):
        return str(self.id)

    def save(self, *args, **kwargs):
        """
        Save page count locally on the object for quick reference,
        but only after the first save.
        """
        self.text = clean_text(self.text)
        self.text_formatted = format_post(self.text)
        super(Post, self).save(*args, **kwargs)

    @cached_property
    def score(self):
        return Vote.objects.get_score(self)['score']

    @cached_property
    def avatar(self):
        return self.author.avatar.url


signals.post_save.connect(update_forum_votes, sender=Vote)
