package com.zhiyu.campus.blog.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.zhiyu.campus.blog.dto.CreatePostRequest;
import com.zhiyu.campus.blog.dto.CreateReplyRequest;
import com.zhiyu.campus.blog.entity.Board;
import com.zhiyu.campus.blog.entity.Post;
import com.zhiyu.campus.blog.entity.PostTag;
import com.zhiyu.campus.blog.entity.Reply;
import com.zhiyu.campus.blog.mapper.BoardMapper;
import com.zhiyu.campus.blog.mapper.PostMapper;
import com.zhiyu.campus.blog.mapper.PostTagMapper;
import com.zhiyu.campus.blog.mapper.ReplyMapper;
import com.zhiyu.campus.blog.vo.PostVO;
import com.zhiyu.campus.blog.vo.ReplyVO;
import com.zhiyu.campus.ai.service.AiAsyncProcessor;
import com.zhiyu.campus.common.BizException;
import com.zhiyu.campus.common.ErrorCode;
import com.zhiyu.campus.tag.entity.Tag;
import com.zhiyu.campus.tag.mapper.TagMapper;
import com.zhiyu.campus.user.entity.User;
import com.zhiyu.campus.user.mapper.UserMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class PostService {

    private static final int MAX_BODY_IN_LIST = 80;

    private final PostMapper postMapper;
    private final ReplyMapper replyMapper;
    private final BoardMapper boardMapper;
    private final PostTagMapper postTagMapper;
    private final TagMapper tagMapper;
    private final UserMapper userMapper;
    private final SensitiveWordChecker sensitiveWordChecker;
    private final InteractionService interactionService;
    private final AiAsyncProcessor aiAsyncProcessor;

    public PostService(PostMapper postMapper, ReplyMapper replyMapper, BoardMapper boardMapper,
                       PostTagMapper postTagMapper, TagMapper tagMapper, UserMapper userMapper,
                       SensitiveWordChecker sensitiveWordChecker,
                       InteractionService interactionService,
                       AiAsyncProcessor aiAsyncProcessor) {
        this.postMapper = postMapper;
        this.replyMapper = replyMapper;
        this.boardMapper = boardMapper;
        this.postTagMapper = postTagMapper;
        this.tagMapper = tagMapper;
        this.userMapper = userMapper;
        this.sensitiveWordChecker = sensitiveWordChecker;
        this.interactionService = interactionService;
        this.aiAsyncProcessor = aiAsyncProcessor;
    }

    @Transactional
    public PostVO create(Long userId, CreatePostRequest request) {
        Board board = boardMapper.selectById(request.boardId());
        if (board == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "板块不存在");
        }
        String hit = sensitiveWordChecker.firstHit(request.title() + request.body());

        Post post = new Post();
        post.setBoardId(board.getId());
        post.setAuthorId(userId);
        post.setTitle(request.title());
        post.setBody(request.body());
        post.setStatus(hit == null ? 0 : 1);
        post.setViewCount(0);
        post.setLikeCount(0);
        post.setFavoriteCount(0);
        post.setCreatedAt(LocalDateTime.now());
        postMapper.insert(post);

        bindTags(post.getId(), request.tagIds());
        submitAiAfterCommit(post.getId());
        return toVO(post, board, loadTagNames(List.of(post.getId())), userId);
    }

    public List<PostVO> list(Long userId, Long boardId, Long tagId, String sort, int page, int size) {
        List<Long> postIds = null;
        if (tagId != null) {
            postIds = postTagMapper.selectList(new LambdaQueryWrapper<PostTag>()
                            .eq(PostTag::getTagId, tagId))
                    .stream().map(PostTag::getPostId).distinct().toList();
            if (postIds.isEmpty()) {
                return List.of();
            }
        }
        LambdaQueryWrapper<Post> wrapper = new LambdaQueryWrapper<Post>()
                .eq(Post::getStatus, 0);
        if (boardId != null) {
            wrapper.eq(Post::getBoardId, boardId);
        }
        if (postIds != null) {
            wrapper.in(Post::getId, postIds);
        }
        if ("hot".equalsIgnoreCase(sort)) {
            wrapper.orderByDesc(Post::getLikeCount).orderByDesc(Post::getViewCount);
        } else {
            wrapper.orderByDesc(Post::getCreatedAt);
        }
        wrapper.orderByDesc(Post::getId);

        Page<Post> result = postMapper.selectPage(
                new Page<>(Math.max(1, page), Math.max(1, Math.min(size, 50))), wrapper);
        List<Post> posts = result.getRecords();
        if (posts.isEmpty()) {
            return List.of();
        }
        Map<Long, Board> boards = boardMap(posts);
        Map<Long, List<String>> tags = loadTagNames(posts.stream().map(Post::getId).toList());
        Map<Long, String> authors = nicknameMap(posts.stream().map(Post::getAuthorId).toList());

        // 批量取“我是否点赞/收藏”，避免原来 toVO() 里每条帖子各查两次库（N+1）
        List<Long> ids = posts.stream().map(Post::getId).toList();
        Set<Long> likedIds = interactionService.likedIds(userId, 2, ids);
        Set<Long> favoritedIds = interactionService.favoritedPostIds(userId, ids);

        List<PostVO> list = new ArrayList<>();
        for (Post p : posts) {
            Board board = boards.get(p.getBoardId());
            list.add(new PostVO(p.getId(), p.getBoardId(), board == null ? null : board.getName(),
                    p.getAuthorId(), authors.get(p.getAuthorId()), p.getTitle(), null, excerpt(p.getBody()),
                    p.getStatus(), p.getViewCount(), p.getLikeCount(), p.getFavoriteCount(),
                    p.getCreatedAt(), tags.getOrDefault(p.getId(), List.of()),
                    likedIds.contains(p.getId()), favoritedIds.contains(p.getId())));
        }
        return list;
    }

    @Transactional
    public PostVO detail(Long userId, Long postId) {
        Post post = requireVisible(userId, postId);
        postMapper.update(null, new LambdaUpdateWrapper<Post>()
                .eq(Post::getId, postId)
                .setSql("view_count = view_count + 1"));
        post.setViewCount(post.getViewCount() + 1);
        return toVO(post, boardMapper.selectById(post.getBoardId()),
                loadTagNames(List.of(postId)), userId);
    }

    @Transactional
    public ReplyVO addReply(Long userId, Long postId, CreateReplyRequest request) {
        Post post = requireVisible(userId, postId);
        if (post.getStatus() != null && post.getStatus() != 0) {
            throw new BizException(ErrorCode.FORBIDDEN, "该帖子不可回复");
        }
        if (request.parentReplyId() != null) {
            Reply parent = replyMapper.selectById(request.parentReplyId());
            if (parent == null || !parent.getPostId().equals(postId)) {
                throw new BizException(ErrorCode.PARAM_ERROR, "父回帖不属于该帖子");
            }
        }
        Reply reply = new Reply();
        reply.setPostId(postId);
        reply.setAuthorId(userId);
        reply.setParentReplyId(request.parentReplyId());
        reply.setContent(request.content());
        reply.setLikeCount(0);
        reply.setStatus(0);
        reply.setCreatedAt(LocalDateTime.now());
        replyMapper.insert(reply);
        return toReplyVO(reply, nicknameOf(userId));
    }

    public List<ReplyVO> replies(Long postId, int page, int size) {
        if (postMapper.selectById(postId) == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "帖子不存在");
        }
        Page<Reply> result = replyMapper.selectPage(
                new Page<>(Math.max(1, page), Math.max(1, Math.min(size, 50))),
                new LambdaQueryWrapper<Reply>()
                        .eq(Reply::getPostId, postId)
                        .eq(Reply::getStatus, 0)
                        .orderByAsc(Reply::getId));
        List<Reply> rows = result.getRecords();
        Map<Long, String> authors = nicknameMap(rows.stream().map(Reply::getAuthorId).toList());
        return rows.stream().map(r -> toReplyVO(r, authors.get(r.getAuthorId()))).toList();
    }

    /** 事务提交后再触发 AI 处理，避免异步线程读不到新帖。 */
    private void submitAiAfterCommit(Long postId) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(
                    new TransactionSynchronization() {
                        @Override
                        public void afterCommit() {
                            aiAsyncProcessor.submit(postId);
                        }
                    });
        } else {
            aiAsyncProcessor.submit(postId);
        }
    }

    // ------------------------------------------------------------ 内部方法

    Post requireVisible(Long userId, Long postId) {
        Post post = postMapper.selectById(postId);
        if (post == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "帖子不存在");
        }
        if (post.getStatus() != null && post.getStatus() != 0
                && !post.getAuthorId().equals(userId)) {
            throw new BizException(ErrorCode.NOT_FOUND, "帖子不存在或未通过审核");
        }
        return post;
    }

    private void bindTags(Long postId, List<Long> tagIds) {
        if (tagIds == null || tagIds.isEmpty()) {
            return;
        }
        List<Long> valid = tagMapper.selectList(new LambdaQueryWrapper<Tag>()
                        .in(Tag::getId, tagIds))
                .stream().map(Tag::getId).toList();
        for (Long tagId : valid) {
            PostTag link = new PostTag();
            link.setPostId(postId);
            link.setTagId(tagId);
            link.setSource(1);
            link.setCreatedAt(LocalDateTime.now());
            postTagMapper.insert(link);
        }
    }

    private Map<Long, List<String>> loadTagNames(List<Long> postIds) {
        Map<Long, List<String>> result = new LinkedHashMap<>();
        if (postIds.isEmpty()) {
            return result;
        }
        List<PostTag> links = postTagMapper.selectList(
                new LambdaQueryWrapper<PostTag>().in(PostTag::getPostId, postIds));
        if (links.isEmpty()) {
            return result;
        }
        Map<Long, String> names = tagMapper.selectList(new LambdaQueryWrapper<Tag>()
                        .in(Tag::getId, links.stream().map(PostTag::getTagId).distinct().toList()))
                .stream().collect(Collectors.toMap(Tag::getId, Tag::getName));
        for (PostTag link : links) {
            result.computeIfAbsent(link.getPostId(), k -> new ArrayList<>())
                    .add(names.getOrDefault(link.getTagId(), String.valueOf(link.getTagId())));
        }
        return result;
    }

    private Map<Long, Board> boardMap(List<Post> posts) {
        List<Long> ids = posts.stream().map(Post::getBoardId).distinct().toList();
        return boardMapper.selectList(new LambdaQueryWrapper<Board>().in(Board::getId, ids))
                .stream().collect(Collectors.toMap(Board::getId, b -> b));
    }

    private Map<Long, String> nicknameMap(List<Long> userIds) {
        if (userIds.isEmpty()) {
            return Map.of();
        }
        return userMapper.selectList(new LambdaQueryWrapper<User>()
                        .in(User::getId, userIds.stream().distinct().toList()))
                .stream().collect(Collectors.toMap(User::getId, User::getNickname));
    }

    private String nicknameOf(Long userId) {
        User u = userMapper.selectById(userId);
        return u == null ? null : u.getNickname();
    }

    private String excerpt(String body) {
        if (body == null) {
            return null;
        }
        return body.length() <= MAX_BODY_IN_LIST ? body : body.substring(0, MAX_BODY_IN_LIST) + "…";
    }

    private ReplyVO toReplyVO(Reply r, String nickname) {
        return new ReplyVO(r.getId(), r.getPostId(), r.getAuthorId(), nickname,
                r.getParentReplyId(), r.getContent(), r.getLikeCount(), r.getCreatedAt());
    }

    private PostVO toVO(Post p, Board board, Map<Long, List<String>> tags, Long userId) {
        boolean liked = interactionService.liked(userId, 2, p.getId());
        boolean favorited = interactionService.favorited(userId, p.getId());
        return new PostVO(p.getId(), p.getBoardId(), board == null ? null : board.getName(),
                p.getAuthorId(), nicknameOf(p.getAuthorId()), p.getTitle(), p.getBody(), excerpt(p.getBody()),
                p.getStatus(), p.getViewCount(), p.getLikeCount(), p.getFavoriteCount(),
                p.getCreatedAt(), tags.getOrDefault(p.getId(), List.of()), liked, favorited);
    }
}
